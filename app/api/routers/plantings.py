from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.dependencies.plantings import PlantingServiceDep
from app.core.dependencies.revision import ExpectedPlanRevisionDep
from app.schemas.planting import PlantingCreateSchema, PlantingMutationReadSchema, PlantingPatchSchema

router = APIRouter(prefix='/projects/{project_id}/plans/{plan_id}/plantings', tags=['Посадки'])


@router.post('', response_model=PlantingMutationReadSchema, status_code=status.HTTP_201_CREATED)
async def add_planting(
    project_id: int,
    plan_id: int,
    data: PlantingCreateSchema,
    expected_revision: ExpectedPlanRevisionDep,
    service: PlantingServiceDep,
    response: Response,
):
    """Добавляет проверенную посадку в план."""

    result = await service.add_planting(
        project_id=project_id,
        plan_id=plan_id,
        expected_revision=expected_revision,
        data=data,
    )
    response.headers['ETag'] = f'"{result.plan_revision}"'
    return result


@router.patch('/{planting_id}', response_model=PlantingMutationReadSchema)
async def update_planting(
    project_id: int,
    plan_id: int,
    planting_id: UUID,
    data: PlantingPatchSchema,
    expected_revision: ExpectedPlanRevisionDep,
    service: PlantingServiceDep,
    response: Response,
):
    """Перемещает посадку или изменяет её тип."""

    result = await service.update_planting(
        project_id=project_id,
        plan_id=plan_id,
        planting_id=planting_id,
        expected_revision=expected_revision,
        data=data,
    )
    response.headers['ETag'] = f'"{result.plan_revision}"'
    return result


@router.delete('/{planting_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_planting(
    project_id: int,
    plan_id: int,
    planting_id: UUID,
    expected_revision: ExpectedPlanRevisionDep,
    service: PlantingServiceDep,
    response: Response,
) -> None:
    """Удаляет посадку из плана."""

    revision = await service.delete_planting(
        project_id=project_id,
        plan_id=plan_id,
        planting_id=planting_id,
        expected_revision=expected_revision,
    )
    response.headers['ETag'] = f'"{revision}"'
