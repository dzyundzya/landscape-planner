from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.analyses import AnalysisService


def get_analysis_service(async_session: DBSession) -> AnalysisService:
    """Создаёт сервис анализа проектов."""

    return AnalysisService(async_session=async_session)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
