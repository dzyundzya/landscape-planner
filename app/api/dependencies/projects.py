from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.projects import ProjectService


def get_project_service(async_session: DBSession) -> ProjectService:
    """Создает сервис проектов."""

    return ProjectService(async_session=async_session)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
