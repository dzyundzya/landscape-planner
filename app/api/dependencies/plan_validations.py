from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.plan_validations import PlanValidationService


def get_plan_validation_service(async_session: DBSession) -> PlanValidationService:
    """Создаёт сервис результатов Validator."""

    return PlanValidationService(async_session=async_session)


PlanValidationServiceDep = Annotated[PlanValidationService, Depends(get_plan_validation_service)]
