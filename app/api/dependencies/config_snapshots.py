from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.config_snapshots import ConfigSnapshotService


def get_config_snapshot_service(async_session: DBSession) -> ConfigSnapshotService:
    """Создаёт сервис снимков настроек проекта."""

    return ConfigSnapshotService(async_session=async_session)


ConfigSnapshotServiceDep = Annotated[ConfigSnapshotService, Depends(get_config_snapshot_service)]
