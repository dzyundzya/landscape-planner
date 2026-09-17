from typing import Annotated

from fastapi import Depends

from app.core.dependencies.session import DBSession
from app.services.jobs import JobService


def get_job_service(async_session: DBSession) -> JobService:
    """Создаёт сервис фоновых задач."""

    return JobService(async_session=async_session)


JobServiceDep = Annotated[JobService, Depends(get_job_service)]
