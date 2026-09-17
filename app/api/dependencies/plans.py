from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.plans import PlanService


def get_plan_service(async_session: DBSession) -> PlanService:
    """Создаёт сервис планов озеленения."""

    return PlanService(async_session=async_session)


PlanServiceDep = Annotated[PlanService, Depends(get_plan_service)]
