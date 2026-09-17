from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.project_files import ProjectFileService


def get_project_file_service(async_session: DBSession) -> ProjectFileService:
    """Создаёт сервис исходных файлов проектов."""

    return ProjectFileService(async_session=async_session)


ProjectFileServiceDep = Annotated[ProjectFileService, Depends(get_project_file_service)]
