from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.plantings import PlantingService


def get_planting_service(async_session: DBSession) -> PlantingService:
    """Создаёт сервис посадок плана."""

    return PlantingService(async_session=async_session)


PlantingServiceDep = Annotated[PlantingService, Depends(get_planting_service)]
