from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NormativeRulesStatus,
    PlanModel,
    PlanStatus,
    PlanValidationModel,
    ValidationStatus,
)
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.plan_validations import PlanValidationCRUDRepository
from app.repositories.crud.plans import PlanCRUDRepository
from app.schemas.plan_validation import (
    CheckResultSchema,
    PlanValidationPublishSchema,
    ValidationSummarySchema,
)
from app.services.base import BaseService
from app.services.exceptions.plan_validations import (
    InvalidPlanValidationError,
    PlanValidationUnavailableError,
)
from app.services.exceptions.plans import PlanNotFoundError
from app.services.exceptions.plantings import PlanRevisionConflictError


class PlanValidationService(BaseService[PlanValidationCRUDRepository]):
    """Публикация и чтение проверок конкретной ревизии плана."""

    repository_class = PlanValidationCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.plan_repository = PlanCRUDRepository(async_session=async_session)
        self.config_repository = ConfigSnapshotCRUDRepository(async_session=async_session)

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

        self._validate_planting_references(plan=plan, checks=data.checks)
        config = await self.config_repository.get_obj_by_id(obj_id=plan.config_snapshot_id)
        if config is None:
            raise InvalidPlanValidationError('Снимок конфигурации плана недоступен')

        checks = list(data.checks)
        if config.rules_status is NormativeRulesStatus.NEEDS_VERIFICATION:
            checks.append(
                CheckResultSchema(
                    check_type='normative_rules_status',
                    status=ValidationStatus.NEEDS_VERIFICATION,
                    reason='Normative rules have not been verified',
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
            )
        )
        plan.status = self._to_plan_status(status=status)
        await self.session.commit()
        logger.info(
            'Ревизия плана проверена: validation_id={}, plan_id={}, revision={}, status={}',
            validation.id,
            plan.id,
            plan.revision,
            validation.status,
        )
        return validation

    @staticmethod
    def _validate_planting_references(plan: PlanModel, checks: list[CheckResultSchema]) -> None:
        planting_ids: set[UUID] = {planting.public_id for planting in plan.plantings}
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
