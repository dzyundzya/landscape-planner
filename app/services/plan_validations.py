from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    JobModel,
    JobStatus,
    JobType,
    NormativeRulesStatus,
    PlanModel,
    PlanStatus,
    PlantCatalogStatus,
    PlanValidationModel,
    ValidationStatus,
)
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.plan_validations import PlanValidationCRUDRepository
from app.repositories.crud.plans import PlanCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.schemas.config_snapshot import CalculationConfigSnapshotSchema
from app.schemas.plan_validation import (
    CheckResultSchema,
    PlanValidationJobInputSchema,
    PlanValidationPublishSchema,
    ValidationSummarySchema,
)
from app.schemas.planting import PlantingReadSchema
from app.services.base import BaseService
from app.services.exceptions.plan_validations import (
    InvalidPlanValidationError,
    PlanValidationAlreadyExistsError,
    PlanValidationUnavailableError,
)
from app.services.exceptions.plans import PlanNotFoundError
from app.services.exceptions.plantings import PlanRevisionConflictError
from app.services.jobs import JobService


class PlanValidationService(BaseService[PlanValidationCRUDRepository]):
    """Публикация и чтение проверок конкретной ревизии плана."""

    repository_class = PlanValidationCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.plan_repository = PlanCRUDRepository(async_session=async_session)
        self.config_repository = ConfigSnapshotCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.job_repository = JobCRUDRepository(async_session=async_session)

    async def enqueue_validation(self, project_id: int, plan_id: int, expected_revision: int) -> JobModel:
        """Фиксирует текущую ревизию плана и ставит полную проверку в очередь."""

        plan = await self.plan_repository.get_plan_for_update(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        if plan.revision != expected_revision:
            raise PlanRevisionConflictError(expected=expected_revision, actual=plan.revision)
        existing = await self.repository.get_for_plan_revision(plan_id=plan.id, plan_revision=plan.revision)
        if existing is not None:
            raise PlanValidationAlreadyExistsError(plan_id=plan.id, plan_revision=plan.revision)

        active_job = await self.job_repository.get_active_plan_validation(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if active_job is not None:
            return active_job

        project_file = await self.project_file_repository.get_obj_by_id(obj_id=plan.project_file_id)
        config = await self.config_repository.get_obj_by_id(obj_id=plan.config_snapshot_id)
        if project_file is None or project_file.project_id != project_id:
            raise InvalidPlanValidationError('Исходный файл плана недоступен')
        if (
            config is None
            or config.territory_type is None
            or config.rules_version is None
            or config.rules_sha256 is None
            or config.plant_catalog_status is None
            or config.plant_catalog_version is None
            or config.plant_catalog_sha256 is None
        ):
            raise InvalidPlanValidationError('Неизменяемая конфигурация плана неполна для проверки')

        job_input = PlanValidationJobInputSchema(
            plan_id=plan.id,
            plan_revision=plan.revision,
            project_file_id=project_file.id,
            project_file_sha256=project_file.sha256,
            config_snapshot_id=config.id,
            config=CalculationConfigSnapshotSchema(
                content_sha256=config.content_sha256,
                coordinate_unit=config.coordinate_unit,
                unit_scale_to_meters=config.unit_scale_to_meters,
                boundary=config.boundary,
                layer_mappings=config.layer_mappings,
                generation=config.generation,
                territory_type=config.territory_type,
                rules_status=config.rules_status,
                rules_version=config.rules_version,
                rules_sha256=config.rules_sha256,
                plant_catalog_status=config.plant_catalog_status,
                plant_catalog_version=config.plant_catalog_version,
                plant_catalog_sha256=config.plant_catalog_sha256,
            ),
            plantings=[PlantingReadSchema.model_validate(planting) for planting in plan.plantings],
        )
        return await JobService(async_session=self.session).enqueue_job(
            project_id=project_id,
            project_file_id=project_file.id,
            job_type=JobType.VALIDATE_PLAN,
            input_data=job_input.model_dump(mode='json'),
        )

    async def get_current_validation(self, project_id: int, plan_id: int) -> PlanValidationModel:
        """Возвращает проверку только для актуальной ревизии плана."""

        plan = await self.plan_repository.get_plan_for_project(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        validation = await self.repository.get_for_plan_revision(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if validation is None:
            raise PlanValidationUnavailableError(plan_id=plan.id, plan_revision=plan.revision)
        return validation

    async def publish_validation(
        self,
        project_id: int,
        plan_id: int,
        plan_revision: int,
        data: PlanValidationPublishSchema,
    ) -> PlanValidationModel:
        """Атомарно сохраняет Validator и меняет статус той же ревизии плана."""

        plan = await self.plan_repository.get_plan_for_update(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        if plan.revision != plan_revision:
            raise PlanRevisionConflictError(expected=plan_revision, actual=plan.revision)

        existing = await self.repository.get_for_plan_revision(
            plan_id=plan.id,
            plan_revision=plan.revision,
        )
        if existing is not None:
            return existing

        validation = await self.create_validation_for_plan(
            plan=plan,
            data=data,
            planting_ids={planting.public_id for planting in plan.plantings},
        )
        await self.session.commit()
        logger.info(
            'Ревизия плана проверена: validation_id={}, plan_id={}, revision={}, status={}',
            validation.id,
            plan.id,
            plan.revision,
            validation.status,
        )
        return validation

    async def publish_job_validation(
        self,
        job_id: int,
        data: PlanValidationPublishSchema,
    ) -> PlanValidationModel:
        """Атомарно публикует повторную проверку и завершает её Job."""

        job = await self.job_repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise InvalidPlanValidationError(f'Задача проверки с id={job_id} не найдена')
        if job.type is not JobType.VALIDATE_PLAN:
            raise InvalidPlanValidationError(f'Задача с id={job.id} не является проверкой плана')
        if job.status is not JobStatus.RUNNING:
            raise InvalidPlanValidationError(f'Задача проверки с id={job.id} не выполняется')
        job_input = self._parse_job_input(job=job)

        plan = await self.plan_repository.get_plan_for_update(
            plan_id=job_input.plan_id,
            project_id=job.project_id,
        )
        if plan is None:
            raise PlanNotFoundError(plan_id=job_input.plan_id)
        if plan.revision != job_input.plan_revision:
            raise PlanRevisionConflictError(expected=job_input.plan_revision, actual=plan.revision)
        if plan.project_file_id != job_input.project_file_id or plan.config_snapshot_id != job_input.config_snapshot_id:
            raise InvalidPlanValidationError('План не соответствует зафиксированным входам проверки')
        if not self._plantings_match_snapshot(plan=plan, job_input=job_input):
            raise InvalidPlanValidationError('Посадки плана не соответствуют зафиксированной ревизии проверки')

        existing = await self.repository.get_for_plan_revision(plan_id=plan.id, plan_revision=plan.revision)
        if existing is None:
            validation = await self.create_validation_for_plan(
                plan=plan,
                data=data,
                planting_ids={planting.public_id for planting in plan.plantings},
            )
        else:
            validation = existing

        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = {
            'validation_id': validation.id,
            'plan_id': plan.id,
            'plan_revision': plan.revision,
            'status': validation.status.value,
        }
        job.error = None
        job.finished_at = datetime.now(UTC)
        await self.session.commit()
        logger.info(
            'Повторная проверка опубликована: validation_id={}, plan_id={}, revision={}, job_id={}, status={}',
            validation.id,
            plan.id,
            plan.revision,
            job.id,
            validation.status,
        )
        return validation

    async def create_validation_for_plan(
        self,
        plan: PlanModel,
        data: PlanValidationPublishSchema,
        planting_ids: set[UUID],
    ) -> PlanValidationModel:
        """Создаёт проверку в текущей транзакции без самостоятельного commit."""

        self._validate_planting_references(planting_ids=planting_ids, checks=data.checks)
        config = await self.config_repository.get_obj_by_id(obj_id=plan.config_snapshot_id)
        if config is None:
            raise InvalidPlanValidationError('Снимок конфигурации плана недоступен')

        checks = list(data.checks)
        if config.rules_status is NormativeRulesStatus.NEEDS_VERIFICATION:
            checks.append(
                CheckResultSchema(
                    check_type='normative_rules_status',
                    status=ValidationStatus.NEEDS_VERIFICATION,
                    reason='Нормативный справочник не проверен',
                )
            )
        if config.plant_catalog_status is not PlantCatalogStatus.VERIFIED:
            checks.append(
                CheckResultSchema(
                    check_type='plant_catalog_status',
                    status=ValidationStatus.NEEDS_VERIFICATION,
                    reason='Происхождение справочника растений не подтверждено',
                )
            )

        summary = self._build_summary(checks=checks)
        status = self._get_validation_status(summary=summary)
        validation = await self.repository.create_obj(
            new_obj=PlanValidationModel(
                plan_id=plan.id,
                plan_revision=plan.revision,
                status=status,
                validator_version=data.validator_version,
                checks=[check.model_dump(mode='json') for check in checks],
                summary=summary.model_dump(mode='json'),
                rules_status=config.rules_status,
                rules_version=config.rules_version,
                rules_sha256=config.rules_sha256,
                plant_catalog_status=config.plant_catalog_status,
                plant_catalog_version=config.plant_catalog_version,
                plant_catalog_sha256=config.plant_catalog_sha256,
            )
        )
        plan.status = self._to_plan_status(status=status)
        return validation

    @staticmethod
    def _validate_planting_references(planting_ids: set[UUID], checks: list[CheckResultSchema]) -> None:
        checked_planting_ids = {check.planting_id for check in checks if check.planting_id is not None}
        unknown_ids = sorted(checked_planting_ids - planting_ids, key=str)
        if unknown_ids:
            raise InvalidPlanValidationError(f'Проверка ссылается на неизвестную посадку с id={unknown_ids[0]}')
        missing_ids = sorted(planting_ids - checked_planting_ids, key=str)
        if missing_ids:
            raise InvalidPlanValidationError(f'В проверке отсутствуют результаты для посадки с id={missing_ids[0]}')

    @staticmethod
    def _build_summary(checks: list[CheckResultSchema]) -> ValidationSummarySchema:
        return ValidationSummarySchema(
            total=len(checks),
            passed=sum(check.status is ValidationStatus.PASSED for check in checks),
            failed=sum(check.status is ValidationStatus.FAILED for check in checks),
            needs_verification=sum(check.status is ValidationStatus.NEEDS_VERIFICATION for check in checks),
        )

    @staticmethod
    def _get_validation_status(summary: ValidationSummarySchema) -> ValidationStatus:
        if summary.failed:
            return ValidationStatus.FAILED
        if summary.needs_verification:
            return ValidationStatus.NEEDS_VERIFICATION
        return ValidationStatus.PASSED

    @staticmethod
    def _to_plan_status(status: ValidationStatus) -> PlanStatus:
        if status is ValidationStatus.FAILED:
            return PlanStatus.INVALID
        if status is ValidationStatus.PASSED:
            return PlanStatus.VERIFIED
        return PlanStatus.NEEDS_VERIFICATION

    @staticmethod
    def _parse_job_input(job: JobModel) -> PlanValidationJobInputSchema:
        try:
            job_input = PlanValidationJobInputSchema.model_validate(job.input_data)
        except ValidationError as exc:
            raise InvalidPlanValidationError(f'Задача с id={job.id} содержит некорректные входы проверки') from exc
        if job.project_file_id != job_input.project_file_id:
            raise InvalidPlanValidationError(f'Задача с id={job.id} не соответствует исходному файлу проверки')
        return job_input

    @staticmethod
    def _plantings_match_snapshot(plan: PlanModel, job_input: PlanValidationJobInputSchema) -> bool:
        current = sorted(
            (PlantingReadSchema.model_validate(planting).model_dump(mode='json') for planting in plan.plantings),
            key=lambda planting: planting['public_id'],
        )
        expected = sorted(
            (planting.model_dump(mode='json') for planting in job_input.plantings),
            key=lambda planting: planting['public_id'],
        )
        return current == expected
