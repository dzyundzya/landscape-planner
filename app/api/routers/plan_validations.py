from fastapi import APIRouter, status

from app.api.dependencies.plan_validations import PlanValidationServiceDep
from app.core.dependencies.revision import ExpectedPlanRevisionDep
from app.schemas.job import JobReadSchema
from app.schemas.plan_validation import PlanValidationReadSchema

router = APIRouter(prefix='/projects/{project_id}/plans/{plan_id}', tags=['Plan validations'])


@router.post('/validate', response_model=JobReadSchema, status_code=status.HTTP_202_ACCEPTED)
async def validate_plan(
    project_id: int,
    plan_id: int,
    expected_revision: ExpectedPlanRevisionDep,
    service: PlanValidationServiceDep,
):
    """Ставит повторную проверку текущей ревизии плана в очередь."""

    return await service.enqueue_validation(
        project_id=project_id,
        plan_id=plan_id,
        expected_revision=expected_revision,
    )


@router.get('/report', response_model=PlanValidationReadSchema)
async def get_plan_report(project_id: int, plan_id: int, service: PlanValidationServiceDep):
    """Возвращает объяснимые проверки актуальной ревизии плана."""

    return await service.get_current_validation(project_id=project_id, plan_id=plan_id)
