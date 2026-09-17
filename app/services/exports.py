from datetime import UTC, datetime

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ExportModel,
    FileArtifactKind,
    JobModel,
    JobStatus,
    JobType,
    PlanStatus,
    ValidationStatus,
)
from app.repositories.crud.exports import ExportCRUDRepository
from app.repositories.crud.file_artifacts import FileArtifactCRUDRepository
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.plan_validations import PlanValidationCRUDRepository
from app.repositories.crud.plans import PlanCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.schemas.export import (
    ExportJobInputSchema,
    ExportManifestItemSchema,
    ExportPlanSnapshotSchema,
)
from app.schemas.plan_validation import PlanValidationReadSchema
from app.schemas.planting import PlantingReadSchema
from app.services.base import BaseService
from app.services.exceptions.exports import ExportNotFoundError, ExportPrerequisiteError, InvalidExportError
from app.services.exceptions.jobs import JobNotFoundError, JobStateConflictError
from app.services.exceptions.plans import PlanNotFoundError
from app.services.exceptions.plantings import PlanRevisionConflictError
from app.services.jobs import JobService

REQUIRED_EXPORT_KINDS = (
    FileArtifactKind.RESULT_DXF,
    FileArtifactKind.PLAN_JSON,
    FileArtifactKind.REPORT_JSON,
    FileArtifactKind.REPORT_MARKDOWN,
)


class ExportService(BaseService[ExportCRUDRepository]):
    """Постановка и атомарная публикация неизменяемых экспортов."""

    repository_class = ExportCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.plan_repository = PlanCRUDRepository(async_session=async_session)
        self.validation_repository = PlanValidationCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.job_repository = JobCRUDRepository(async_session=async_session)
        self.artifact_repository = FileArtifactCRUDRepository(async_session=async_session)

    async def enqueue_export(self, project_id: int, plan_id: int, expected_revision: int) -> JobModel:
        """Фиксирует ревизию с проверкой и ставит её экспорт в очередь."""

        plan = await self.plan_repository.get_plan_for_update(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        if plan.revision != expected_revision:
            raise PlanRevisionConflictError(expected=expected_revision, actual=plan.revision)

        completed_export = await self.repository.get_latest_for_plan_revision(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if completed_export is not None:
            completed_job = await self.job_repository.get_obj_by_id(obj_id=completed_export.job_id)
            if completed_job is None:
                raise InvalidExportError(f'Export with id={completed_export.id} has no job')
            return completed_job

        active_job = await self.job_repository.get_active_export(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if active_job is not None:
            return active_job

        validation = await self.validation_repository.get_for_plan_revision(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if validation is None:
            raise ExportPrerequisiteError(f'Plan with id={plan.id} has no validation for revision={plan.revision}')
        if validation.status is not ValidationStatus.PASSED or plan.status is not PlanStatus.VERIFIED:
            raise ExportPrerequisiteError(f'Plan with id={plan.id} revision={plan.revision} is not verified for export')

        project_file = await self.project_file_repository.get_obj_by_id(obj_id=plan.project_file_id)
        if project_file is None or project_file.project_id != project_id:
            raise InvalidExportError('Plan source file is unavailable')

        job_input = ExportJobInputSchema(
            plan_id=plan.id,
            plan_revision=plan.revision,
            project_file_id=project_file.id,
            project_file_sha256=project_file.sha256,
            config_snapshot_id=plan.config_snapshot_id,
            plan=ExportPlanSnapshotSchema(
                generator_version=plan.generator_version,
                generation_summary=plan.generation_summary,
                plantings=[PlantingReadSchema.model_validate(planting) for planting in plan.plantings],
            ),
            validation=PlanValidationReadSchema.model_validate(validation),
        )
        return await JobService(async_session=self.session).enqueue_job(
            project_id=project_id,
            project_file_id=project_file.id,
            job_type=JobType.EXPORT,
            input_data=job_input.model_dump(mode='json'),
        )

    async def get_export(self, project_id: int, plan_id: int, export_id: int) -> ExportModel:
        """Возвращает готовый экспорт внутри заданных проекта и плана."""

        export = await self.repository.get_for_project_plan(
            export_id=export_id,
            project_id=project_id,
            plan_id=plan_id,
        )
        if export is None:
            raise ExportNotFoundError(export_id=export_id)
        return export

    async def publish_export(self, job_id: int, export_version: str) -> ExportModel:
        """Атомарно связывает полный набор файлов и завершает задачу экспорта."""

        existing = await self.repository.get_by_job_id(job_id=job_id)
        if existing is not None:
            return existing

        normalized_version = export_version.strip()
        if not normalized_version or len(normalized_version) > 100:
            raise InvalidExportError('Export version must contain from 1 to 100 characters')

        job = await self.job_repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        if job.type is not JobType.EXPORT:
            raise InvalidExportError(f'Job with id={job.id} is not an export job')
        if job.status is not JobStatus.RUNNING:
            raise JobStateConflictError(job_id=job.id, status=job.status)

        job_input = self._parse_job_input(job=job)
        validation = await self.validation_repository.get_for_plan_revision(
            plan_id=job_input.plan_id,
            plan_revision=job_input.plan_revision,
        )
        if validation is None or validation.id != job_input.validation.id:
            raise InvalidExportError('Export validation snapshot does not match persisted validation')
        if validation.status is not ValidationStatus.PASSED:
            raise InvalidExportError('Export validation is not passed')

        artifacts = await self.artifact_repository.get_artifacts_for_job(job_id=job.id)
        artifacts_by_kind = {artifact.kind: artifact for artifact in artifacts}
        if set(artifacts_by_kind) != set(REQUIRED_EXPORT_KINDS):
            raise InvalidExportError('Export job must publish result.dxf, plan.json, report.json and report.md')
        if any(
            artifact.project_id != job.project_id
            or artifact.project_file_id != job_input.project_file_id
            or artifact.export_id is not None
            for artifact in artifacts
        ):
            raise InvalidExportError('Export artifacts do not match the fixed job inputs')

        manifest = [
            ExportManifestItemSchema(
                artifact_id=artifacts_by_kind[kind].id,
                kind=kind,
                format=artifacts_by_kind[kind].format,
                download_name=artifacts_by_kind[kind].download_name,
                size_bytes=artifacts_by_kind[kind].size_bytes,
                sha256=artifacts_by_kind[kind].sha256,
            )
            for kind in REQUIRED_EXPORT_KINDS
        ]
        export = await self.repository.create_obj(
            new_obj=ExportModel(
                project_id=job.project_id,
                plan_id=job_input.plan_id,
                plan_revision=job_input.plan_revision,
                validation_id=validation.id,
                job_id=job.id,
                export_version=normalized_version,
                manifest=[item.model_dump(mode='json') for item in manifest],
            )
        )
        export.artifacts = artifacts

        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = {
            'export_id': export.id,
            'plan_id': export.plan_id,
            'plan_revision': export.plan_revision,
            'artifacts': [{'artifact_id': item.artifact_id, 'kind': item.kind.value} for item in manifest],
        }
        job.error = None
        job.finished_at = datetime.now(UTC)
        await self.session.commit()
        logger.info(
            'Экспорт опубликован: export_id={}, plan_id={}, revision={}, job_id={}',
            export.id,
            export.plan_id,
            export.plan_revision,
            job.id,
        )
        return export

    @staticmethod
    def _parse_job_input(job: JobModel) -> ExportJobInputSchema:
        try:
            job_input = ExportJobInputSchema.model_validate(job.input_data)
        except ValidationError as exc:
            raise InvalidExportError(f'Job with id={job.id} has invalid export inputs') from exc
        if job.project_file_id != job_input.project_file_id:
            raise InvalidExportError(f'Job with id={job.id} does not match export source file')
        return job_input
