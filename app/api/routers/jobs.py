from fastapi import APIRouter

from app.api.dependencies.jobs import JobServiceDep
from app.schemas.job import JobReadSchema

router = APIRouter(prefix='/jobs', tags=['Фоновые задачи'])


@router.get('/{job_id}', response_model=JobReadSchema)
async def get_job(job_id: int, service: JobServiceDep):
    """Возвращает состояние фоновой задачи."""

    return await service.get_job_by_id(job_id=job_id)
