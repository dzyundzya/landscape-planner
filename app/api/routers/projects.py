from fastapi import APIRouter, status

from app.api.dependencies.projects import ProjectServiceDep
from app.core.dependencies.pagination import PaginationDep
from app.schemas.project import ProjectCreateSchema, ProjectPageSchema, ProjectReadSchema

router = APIRouter(prefix='/projects', tags=['Projects'])


@router.get('/', response_model=ProjectPageSchema)
async def get_projects(
    service: ProjectServiceDep,
    pagination: PaginationDep,
):
    """Возвращает страницу проектов."""

    return await service.get_projects_page(page=pagination.page, limit=pagination.limit)


@router.get('/{project_id}', response_model=ProjectReadSchema)
async def get_project(
    project_id: int,
    service: ProjectServiceDep,
):
    """Возвращает проект по ID."""

    return await service.get_project_by_id(project_id=project_id)


@router.post('/', response_model=ProjectReadSchema, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreateSchema,
    service: ProjectServiceDep,
):
    """Создает проект."""

    return await service.create_project(data=data)
