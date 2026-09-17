from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.file_artifacts import FileArtifactService


def get_file_artifact_service(async_session: DBSession) -> FileArtifactService:
    """Создаёт сервис сформированных файлов проекта."""

    return FileArtifactService(async_session=async_session)


FileArtifactServiceDep = Annotated[FileArtifactService, Depends(get_file_artifact_service)]
