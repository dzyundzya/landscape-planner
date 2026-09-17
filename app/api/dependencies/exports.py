from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.exports import ExportService


def get_export_service(async_session: DBSession) -> ExportService:
    """Создаёт сервис экспортов плана."""

    return ExportService(async_session=async_session)


ExportServiceDep = Annotated[ExportService, Depends(get_export_service)]
