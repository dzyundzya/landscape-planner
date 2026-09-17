from fastapi import APIRouter, Response, status

from app.api.dependencies.plans import PlanServiceDep
from app.schemas.job import JobReadSchema
from app.schemas.plan import PlanReadSchema

router = APIRouter(prefix='/projects/{project_id}/plans', tags=['Plans'])


@router.post('', response_model=JobReadSchema, status_code=status.HTTP_202_ACCEPTED)
async def generate_plan(project_id: int, service: PlanServiceDep):
    """Ставит генерацию плана по текущей конфигурации в очередь."""

    return await service.enqueue_plan_generation(project_id=project_id)


@router.get('/{plan_id}', response_model=PlanReadSchema)
async def get_plan(project_id: int, plan_id: int, service: PlanServiceDep, response: Response):
    """Возвращает план озеленения."""

    plan = await service.get_plan(project_id=project_id, plan_id=plan_id)
    response.headers['ETag'] = f'"{plan.revision}"'
    return plan
