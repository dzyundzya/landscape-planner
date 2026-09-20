from dataclasses import dataclass
from functools import partial
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cad import normalize_dxf
from app.domain import NormalizationOptions
from app.geometry import build_restriction_zones, prepare_project_geometry
from app.models import JobModel, ProjectFileFormat, ProjectFileStatus
from app.planning import ValidationPlanting, validate_plan_geometry
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.rules import load_rule_set
from app.schemas.plan_validation import PlanValidationJobInputSchema, PlanValidationPublishSchema
from app.services.exceptions.plan_validations import InvalidPlanValidationError
from app.services.jobs import JobService
from app.services.plan_validations import PlanValidationService
from app.storage import LocalFileStorage
from app.worker.dispatcher import OwnershipGuard
from app.worker.metrics import run_measured_operation


@dataclass(frozen=True, slots=True)
class _PlanValidationInput:
    """Проверенные входы тяжёлой повторной проверки."""

    source_path: Path
    snapshot: PlanValidationJobInputSchema


class PlanValidationJobHandler:
    """Повторно проверяет зафиксированную ревизию плана вне процесса API."""

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
            validation_input = await self._load_input(session=session, job=job)
            await JobService(session).update_stage(job_id=job.id, stage='validating_plan')

        validation = await run_measured_operation(
            partial(self._validate, validation_input),
            job_id=job.id,
            operation_name='validate_plan',
            source_path=validation_input.source_path,
        )
        await ensure_ownership()

        async with self.session_factory() as session:
            await PlanValidationService(session).publish_job_validation(
                job_id=job.id,
                data=validation,
            )

    async def _load_input(self, session: AsyncSession, job: JobModel) -> _PlanValidationInput:
        try:
            snapshot = PlanValidationJobInputSchema.model_validate(job.input_data)
        except ValidationError as exc:
            raise InvalidPlanValidationError('Задача содержит некорректный снимок входов проверки') from exc

        project_file = await ProjectFileCRUDRepository(session).get_obj_by_id(obj_id=snapshot.project_file_id)
        if project_file is None or project_file.project_id != job.project_id:
            raise InvalidPlanValidationError('Исходный файл проверки не соответствует проекту')
        if project_file.format is not ProjectFileFormat.DXF or project_file.status is not ProjectFileStatus.READY:
            raise InvalidPlanValidationError('Для проверки требуется готовый DXF-файл')
        if project_file.sha256 != snapshot.project_file_sha256 or job.project_file_id != project_file.id:
            raise InvalidPlanValidationError('Исходный файл изменился после постановки проверки в очередь')
        return _PlanValidationInput(
            source_path=self.storage.get_path(project_file.storage_key),
            snapshot=snapshot,
        )

    def _validate(self, data: _PlanValidationInput) -> PlanValidationPublishSchema:
        snapshot = data.snapshot
        rule_set = load_rule_set(self.rules_path)
        if rule_set.data.version != snapshot.config.rules_version or rule_set.sha256 != snapshot.config.rules_sha256:
            raise InvalidPlanValidationError('Нормативный справочник изменился после постановки проверки в очередь')

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
        return validate_plan_geometry(
            project=project,
            restrictions=restrictions,
            plantings=[
                ValidationPlanting(
                    public_id=planting.public_id,
                    type=planting.type,
                    x_m=float(planting.x_m),
                    y_m=float(planting.y_m),
                )
                for planting in snapshot.plantings
            ],
            parameters=snapshot.config.generation,
        )
