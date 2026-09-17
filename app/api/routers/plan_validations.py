from fastapi import APIRouter

from app.api.dependencies.plan_validations import PlanValidationServiceDep
from app.schemas.plan_validation import PlanValidationReadSchema

router = APIRouter(prefix='/projects/{project_id}/plans/{plan_id}', tags=['Plan validations'])


@router.get('/report', response_model=PlanValidationReadSchema)
async def get_plan_report(project_id: int, plan_id: int, service: PlanValidationServiceDep):
    """Возвращает объяснимые проверки актуальной ревизии плана."""

    return await service.get_current_validation(project_id=project_id, plan_id=plan_id)
