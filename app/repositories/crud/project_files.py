from sqlalchemy import func, select

from app.models import ProjectFileModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class ProjectFileCRUDRepository(BaseCRUDRepository[ProjectFileModel]):
    """Операции с исходными файлами проектов."""

    model = ProjectFileModel

    async def get_next_version(self, project_id: int) -> int:
        """Возвращает следующий номер версии исходника проекта."""

        current_version = await self.session.scalar(
            select(func.max(ProjectFileModel.version)).where(ProjectFileModel.project_id == project_id)
        )
        return (current_version or 0) + 1
