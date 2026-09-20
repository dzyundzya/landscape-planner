from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import PlanModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class PlanCRUDRepository(BaseCRUDRepository[PlanModel]):
    """Операции с планами озеленения."""

    model = PlanModel

    async def get_latest_for_config(self, project_id: int, config_snapshot_id: int) -> PlanModel | None:
        """Возвращает последний план текущей конфигурации с посадками."""

        return await self.session.scalar(
            select(PlanModel)
            .options(selectinload(PlanModel.plantings))
            .where(
                PlanModel.project_id == project_id,
                PlanModel.config_snapshot_id == config_snapshot_id,
            )
            .order_by(PlanModel.created_at.desc(), PlanModel.id.desc())
            .limit(1)
        )

    async def get_plan_for_project(self, plan_id: int, project_id: int) -> PlanModel | None:
        """Возвращает план только в пределах указанного проекта."""

        return await self.session.scalar(
            select(PlanModel)
            .options(selectinload(PlanModel.plantings))
            .where(
                PlanModel.id == plan_id,
                PlanModel.project_id == project_id,
            )
        )

    async def get_plan_for_update(self, plan_id: int, project_id: int) -> PlanModel | None:
        """Получает план с посадками и блокировкой ревизии."""

        return await self.session.scalar(
            select(PlanModel)
            .options(selectinload(PlanModel.plantings))
            .where(
                PlanModel.id == plan_id,
                PlanModel.project_id == project_id,
            )
            .with_for_update()
        )

    async def get_by_job_id(self, job_id: int) -> PlanModel | None:
        """Возвращает план, опубликованный заданием."""

        return await self.session.scalar(select(PlanModel).where(PlanModel.job_id == job_id))
