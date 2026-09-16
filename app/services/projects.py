from loguru import logger

from app.models import ProjectModel
from app.repositories.crud.projects import ProjectCRUDRepository
from app.schemas.project import ProjectCreateSchema, ProjectPageSchema
from app.services.base import BaseService
from app.services.exceptions.projects import ProjectNotFoundError


class ProjectService(BaseService[ProjectCRUDRepository]):
    """Бизнес-логика работы с проектами."""

    repository_class = ProjectCRUDRepository

    async def get_project_by_id(self, project_id: int) -> ProjectModel:
        """Возвращает проект по ID."""

        project = await self.repository.get_obj_by_id(obj_id=project_id)

        if project is None:
            raise ProjectNotFoundError(project_id)

        return project

    async def get_projects_page(
        self,
        page: int,
        limit: int,
    ) -> ProjectPageSchema:
        """Возвращает страницу проектов."""

        items, total, pages = await self.repository.get_projects_page(page=page, limit=limit)

        return ProjectPageSchema(
            total=total,
            page=page,
            limit=limit,
            pages=pages,
            items=items,
        )

    async def create_project(self, data: ProjectCreateSchema) -> ProjectModel:
        """Создает новый проект."""

        project = await self.repository.create_obj(new_obj=ProjectModel(**data.model_dump()))
        await self.session.commit()

        logger.info('Проект создан: id={}, name={}', project.id, project.name)

        return project
