from math import ceil

from sqlalchemy import select

from app.models import ProjectModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class ProjectCRUDRepository(BaseCRUDRepository[ProjectModel]):
    """Операции с проектами в базе данных."""

    model = ProjectModel

    async def get_project_by_id_for_update(self, project_id: int) -> ProjectModel | None:
        """Получает проект с блокировкой до завершения транзакции."""

        return await self.session.scalar(select(ProjectModel).where(ProjectModel.id == project_id).with_for_update())

    async def get_projects_page(
        self,
        page: int = 1,
        limit: int = 100,
    ) -> tuple[list[ProjectModel], int, int]:
        """Возвращает страницу проектов."""

        total = await self.get_total()
        pages = ceil(total / limit) if total else 0

        projects = await self.session.scalars(
            select(ProjectModel)
            .order_by(
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )

        return list(projects.all()), total, pages
