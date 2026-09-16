from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_model import BaseModel


class BaseCRUDRepository[ModelType: BaseModel]:
    """Базовый CRUD-репозиторий."""

    model: type[ModelType]

    def __init__(self, async_session: AsyncSession) -> None:
        self.session = async_session

    async def get_obj_by_id(self, obj_id: int) -> ModelType | None:
        """Получает объект по ID."""

        return await self.session.scalar(
            select(ModelType).where(self.model.id == obj_id)
        )

    async def create_obj(self, new_obj: ModelType) -> ModelType:
        """Создает объект."""

        self.session.add(new_obj)

        await self.session.flash()
        await self.session.refresh(new_obj)

        return new_obj

    async def get_total(self) -> int:
        """Считает общее количество объектов."""
        
        return await self.session.scalar(
            select(func.count()).select_from(self.model.id)
        ) or 0
