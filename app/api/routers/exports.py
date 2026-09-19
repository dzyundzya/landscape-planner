from fastapi import APIRouter, status

from app.api.dependencies.exports import ExportServiceDep
from app.core.dependencies.revision import ExpectedPlanRevisionDep
from app.schemas.export import ExportReadSchema
from app.schemas.job import JobReadSchema

router = APIRouter(prefix='/projects/{project_id}/plans/{plan_id}/exports', tags=['Экспорт'])


@router.post('', response_model=JobReadSchema, status_code=status.HTTP_202_ACCEPTED)
async def create_export(
    project_id: int,
    plan_id: int,
    expected_revision: ExpectedPlanRevisionDep,
    service: ExportServiceDep,
):
    """Фиксирует проверенную ревизию и ставит экспорт в очередь."""

    return await service.enqueue_export(
        project_id=project_id,
        plan_id=plan_id,
        expected_revision=expected_revision,
    )


@router.get('/{export_id}', response_model=ExportReadSchema)
async def get_export(project_id: int, plan_id: int, export_id: int, service: ExportServiceDep):
    """Возвращает готовый комплект файлов экспорта."""

    return await service.get_export(project_id=project_id, plan_id=plan_id, export_id=export_id)
