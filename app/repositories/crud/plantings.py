from uuid import UUID

from sqlalchemy import select

from app.models import PlantingModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class PlantingCRUDRepository(BaseCRUDRepository[PlantingModel]):
    """Операции с посадками плана."""

    model = PlantingModel

    async def get_planting_for_plan(self, plan_id: int, public_id: UUID) -> PlantingModel | None:
        """Возвращает посадку только в пределах указанного плана."""

        return await self.session.scalar(
            select(PlantingModel).where(
                PlantingModel.plan_id == plan_id,
                PlantingModel.public_id == public_id,
            )
        )

    async def create_many(self, plantings: list[PlantingModel]) -> list[PlantingModel]:
        """Создаёт набор посадок в текущей транзакции."""

        self.session.add_all(plantings)
        await self.session.flush()
        return plantings

    async def delete_planting(self, planting: PlantingModel) -> None:
        """Удаляет посадку из плана."""

        await self.session.delete(planting)
        await self.session.flush()
