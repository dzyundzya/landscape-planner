from dataclasses import dataclass
from functools import partial
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from anyio import to_thread
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cad import EXPORT_DXF_VERSION, normalize_dxf, write_landscape_dxf
from app.domain import NormalizationOptions
from app.geometry import build_restriction_zones, prepare_project_geometry
from app.models import FileArtifactKind, JobModel, ProjectFileFormat, ProjectFileStatus
from app.reporting import ExportDocuments, build_export_documents
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.rules import load_rule_set
from app.schemas.export import ExportJobInputSchema
from app.services.exceptions.exports import InvalidExportError
from app.services.exports import ExportService
from app.services.file_artifacts import FileArtifactService
from app.services.jobs import JobService
from app.storage import LocalFileStorage
from app.worker.dispatcher import OwnershipGuard


@dataclass(frozen=True, slots=True)
class _ExportInput:
    """Проверенные входы тяжёлой части экспорта."""

    source_path: Path
    snapshot: ExportJobInputSchema


@dataclass(frozen=True, slots=True)
class _ExportOutput:
    """Полный комплект сформированных файлов экспорта."""

    result_dxf: bytes
    documents: ExportDocuments


class ExportJobHandler:
    """Формирует и атомарно публикует файлы проверенной ревизии плана."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: LocalFileStorage,
        rules_path: Path,
        curve_tolerance_m: float,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.rules_path = rules_path
        self.curve_tolerance_m = curve_tolerance_m

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        async with self.session_factory() as session:
            export_input = await self._load_input(session=session, job=job)
            await JobService(session).update_stage(job_id=job.id, stage='preparing_export')

        output = await to_thread.run_sync(partial(self._build_output, job.project_id, export_input))
        await ensure_ownership()

        async with self.session_factory() as session:
            await JobService(session).update_stage(job_id=job.id, stage='publishing_export')
        await ensure_ownership()
        await self._publish(job=job, output=output)

    async def _load_input(self, session: AsyncSession, job: JobModel) -> _ExportInput:
        try:
            snapshot = ExportJobInputSchema.model_validate(job.input_data)
        except ValidationError as exc:
            raise InvalidExportError('Задача содержит некорректный снимок входов экспорта') from exc

        project_file = await ProjectFileCRUDRepository(session).get_obj_by_id(obj_id=snapshot.project_file_id)
        if project_file is None or project_file.project_id != job.project_id:
            raise InvalidExportError('Исходный файл экспорта не соответствует проекту')
        if project_file.format is not ProjectFileFormat.DXF or project_file.status is not ProjectFileStatus.READY:
            raise InvalidExportError('Для экспорта требуется готовый DXF-файл')
        if project_file.sha256 != snapshot.project_file_sha256 or job.project_file_id != project_file.id:
            raise InvalidExportError('Исходный файл изменился после постановки экспорта в очередь')
        return _ExportInput(
            source_path=self.storage.get_path(project_file.storage_key),
            snapshot=snapshot,
        )

    def _build_output(self, project_id: int, data: _ExportInput) -> _ExportOutput:
        snapshot = data.snapshot
        rule_set = load_rule_set(self.rules_path)
        if rule_set.data.version != snapshot.config.rules_version or rule_set.sha256 != snapshot.config.rules_sha256:
            raise InvalidExportError('Нормативный справочник изменился после постановки экспорта в очередь')

        scale = float(snapshot.config.unit_scale_to_meters)
        normalization = normalize_dxf(
            data.source_path,
            options=NormalizationOptions(curve_tolerance=self.curve_tolerance_m / scale),
        )
        project = prepare_project_geometry(
            normalization=normalization,
            unit_scale_to_meters=scale,
            boundary=snapshot.config.boundary.model_dump(mode='json'),
            layer_mappings=[mapping.model_dump(mode='json') for mapping in snapshot.config.layer_mappings],
        )
        restrictions = build_restriction_zones(project=project, rule_set=rule_set)
        if restrictions.issues:
            raise InvalidExportError('При повторном расчёте зон обнаружены неразрешённые ограничения')

        with TemporaryDirectory(prefix='greenplan-export-') as directory:
            output_path = Path(directory) / 'result.dxf'
            dxf_metadata = write_landscape_dxf(
                source_path=data.source_path,
                output_path=output_path,
                plantings=snapshot.plan.plantings,
                transform=project.transform,
                restrictions=restrictions,
            )
            result_dxf = output_path.read_bytes()
        documents = build_export_documents(
            project_id=project_id,
            job_input=snapshot,
            dxf_metadata=dxf_metadata,
        )
        return _ExportOutput(result_dxf=result_dxf, documents=documents)

    async def _publish(self, job: JobModel, output: _ExportOutput) -> None:
        published_keys = []
        async with self.session_factory() as session:
            artifact_service = FileArtifactService(async_session=session, storage=self.storage)
            try:
                sources = (
                    (FileArtifactKind.RESULT_DXF, output.result_dxf),
                    (FileArtifactKind.PLAN_JSON, output.documents.plan_json),
                    (FileArtifactKind.REPORT_JSON, output.documents.report_json),
                    (FileArtifactKind.REPORT_MARKDOWN, output.documents.report_markdown),
                )
                for kind, content in sources:
                    artifact = await artifact_service.create_artifact(
                        project_id=job.project_id,
                        project_file_id=job.project_file_id,
                        job_id=job.id,
                        kind=kind,
                        source=BytesIO(content),
                        commit=False,
                    )
                    published_keys.append(artifact.storage_key)
                await ExportService(session).publish_export(
                    job_id=job.id,
                    export_version=EXPORT_DXF_VERSION,
                )
            except BaseException:
                await session.rollback()
                for storage_key in published_keys:
                    self.storage.delete(storage_key)
                raise
