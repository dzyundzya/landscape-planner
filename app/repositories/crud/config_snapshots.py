from sqlalchemy import func, select

from app.models import ConfigSnapshotModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class ConfigSnapshotCRUDRepository(BaseCRUDRepository[ConfigSnapshotModel]):
    """Операции со снимками настроек проекта."""

    model = ConfigSnapshotModel

    async def get_next_version(self, project_id: int) -> int:
        """Возвращает следующий номер версии настроек проекта."""

        current_version = await self.session.scalar(
            select(func.max(ConfigSnapshotModel.version)).where(ConfigSnapshotModel.project_id == project_id)
        )
        return (current_version or 0) + 1

    async def get_by_content_hash(self, project_id: int, content_sha256: str) -> ConfigSnapshotModel | None:
        """Возвращает ранее сохранённый идентичный снимок проекта."""

        return await self.session.scalar(
            select(ConfigSnapshotModel).where(
                ConfigSnapshotModel.project_id == project_id,
                ConfigSnapshotModel.content_sha256 == content_sha256,
            )
        )

    async def get_latest_for_project(self, project_id: int) -> ConfigSnapshotModel | None:
        """Возвращает последнюю версию настроек проекта."""

        return await self.session.scalar(
            select(ConfigSnapshotModel)
            .where(ConfigSnapshotModel.project_id == project_id)
            .order_by(ConfigSnapshotModel.version.desc(), ConfigSnapshotModel.id.desc())
            .limit(1)
        )
