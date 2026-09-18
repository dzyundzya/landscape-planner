from decimal import Decimal
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlanModel, PlanStatus, PlantingModel, PlantingSource
from app.planning import PlantingCandidate, validate_planting_set
from app.planning import PlantingValidationError as CorePlantingValidationError
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.plans import PlanCRUDRepository
from app.repositories.crud.plantings import PlantingCRUDRepository
from app.schemas.planting import (
    PlantingCreateSchema,
    PlantingMutationReadSchema,
    PlantingPatchSchema,
)
from app.services.base import BaseService
from app.services.exceptions.plans import PlanNotFoundError
from app.services.exceptions.plantings import (
    PlanRevisionConflictError,
    PlantingNotFoundError,
    PlantingValidationError,
)


class PlantingService(BaseService[PlantingCRUDRepository]):
    """Бизнес-логика ручных изменений посадок плана."""

    repository_class = PlantingCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.plan_repository = PlanCRUDRepository(async_session=async_session)
        self.config_repository = ConfigSnapshotCRUDRepository(async_session=async_session)

    async def add_planting(
        self,
        project_id: int,
        plan_id: int,
        expected_revision: int,
        data: PlantingCreateSchema,
    ) -> PlantingMutationReadSchema:
        """Добавляет проверенную ручную посадку и увеличивает ревизию плана."""

        plan = await self._get_plan_for_edit(
            project_id=project_id,
            plan_id=plan_id,
            expected_revision=expected_revision,
        )
        candidate = PlantingCandidate(type=data.type, x_m=data.x_m, y_m=data.y_m)
        await self._validate_candidates(plan=plan, candidates=[*self._to_candidates(plan.plantings), candidate])

        planting = await self.repository.create_obj(
            new_obj=PlantingModel(
                plan_id=plan.id,
                type=data.type,
                source=PlantingSource.MANUAL,
                x_m=Decimal(str(data.x_m)),
                y_m=Decimal(str(data.y_m)),
                species=data.species,
            )
        )
        self._touch_plan(plan=plan)
        await self.session.commit()
        logger.info(
            'Посадка добавлена: planting_id={}, plan_id={}, revision={}', planting.public_id, plan.id, plan.revision
        )
        return PlantingMutationReadSchema(plan_revision=plan.revision, planting=planting)

    async def update_planting(
        self,
        project_id: int,
        plan_id: int,
        planting_id: UUID,
        expected_revision: int,
        data: PlantingPatchSchema,
    ) -> PlantingMutationReadSchema:
        """Перемещает посадку или изменяет её тип и вид."""

        plan = await self._get_plan_for_edit(
            project_id=project_id,
            plan_id=plan_id,
            expected_revision=expected_revision,
        )
        planting = next((item for item in plan.plantings if item.public_id == planting_id), None)
        if planting is None:
            raise PlantingNotFoundError(planting_id=planting_id)

        candidate = PlantingCandidate(
            type=data.type or planting.type,
            x_m=data.x_m if data.x_m is not None else float(planting.x_m),
            y_m=data.y_m if data.y_m is not None else float(planting.y_m),
        )
        other_plantings = [item for item in plan.plantings if item.public_id != planting_id]
        await self._validate_candidates(plan=plan, candidates=[*self._to_candidates(other_plantings), candidate])

        planting.type = candidate.type
        planting.x_m = Decimal(str(candidate.x_m))
        planting.y_m = Decimal(str(candidate.y_m))
        if 'species' in data.model_fields_set:
            planting.species = data.species
        self._touch_plan(plan=plan)
        await self.session.commit()
        logger.info(
            'Посадка изменена: planting_id={}, plan_id={}, revision={}', planting.public_id, plan.id, plan.revision
        )
        return PlantingMutationReadSchema(plan_revision=plan.revision, planting=planting)

    async def delete_planting(
        self,
        project_id: int,
        plan_id: int,
        planting_id: UUID,
        expected_revision: int,
    ) -> int:
        """Удаляет посадку и возвращает новую ревизию плана."""

        plan = await self._get_plan_for_edit(
            project_id=project_id,
            plan_id=plan_id,
            expected_revision=expected_revision,
        )
        planting = next((item for item in plan.plantings if item.public_id == planting_id), None)
        if planting is None:
            raise PlantingNotFoundError(planting_id=planting_id)

        await self.repository.delete_planting(planting=planting)
        self._touch_plan(plan=plan)
        await self.session.commit()
        logger.info('Посадка удалена: planting_id={}, plan_id={}, revision={}', planting_id, plan.id, plan.revision)
        return plan.revision

    async def _get_plan_for_edit(self, project_id: int, plan_id: int, expected_revision: int) -> PlanModel:
        plan = await self.plan_repository.get_plan_for_update(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        if plan.revision != expected_revision:
            raise PlanRevisionConflictError(expected=expected_revision, actual=plan.revision)
        return plan

    async def _validate_candidates(self, plan: PlanModel, candidates: list[PlantingCandidate]) -> None:
        config = await self.config_repository.get_obj_by_id(obj_id=plan.config_snapshot_id)
        if config is None:
            raise PlantingValidationError('Снимок конфигурации плана недоступен')
        try:
            validate_planting_set(
                candidates=candidates,
                boundary=config.boundary,
                generation=config.generation,
            )
        except CorePlantingValidationError as exc:
            raise PlantingValidationError(str(exc)) from exc

    @staticmethod
    def _to_candidates(plantings: list[PlantingModel]) -> list[PlantingCandidate]:
        return [PlantingCandidate(type=item.type, x_m=float(item.x_m), y_m=float(item.y_m)) for item in plantings]

    @staticmethod
    def _touch_plan(plan: PlanModel) -> None:
        plan.revision += 1
        plan.status = PlanStatus.NEEDS_VERIFICATION
