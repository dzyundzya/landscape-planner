from fastapi import APIRouter

from app.api.dependencies.config_snapshots import ConfigSnapshotServiceDep
from app.schemas.config_snapshot import ConfigSnapshotReadSchema, ConfigSnapshotUpsertSchema

router = APIRouter(prefix='/projects/{project_id}/config', tags=['Project configuration'])


@router.get('', response_model=ConfigSnapshotReadSchema)
async def get_project_config(
    project_id: int,
    service: ConfigSnapshotServiceDep,
):
    """Возвращает последнюю конфигурацию текущего анализа проекта."""

    return await service.get_current_config(project_id=project_id)


@router.put('', response_model=ConfigSnapshotReadSchema)
async def save_project_config(
    project_id: int,
    data: ConfigSnapshotUpsertSchema,
    service: ConfigSnapshotServiceDep,
):
    """Подтверждает настройки текущего анализа проекта."""

    return await service.save_current_config(project_id=project_id, data=data)
