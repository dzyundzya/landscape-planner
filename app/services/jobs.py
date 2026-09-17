from copy import deepcopy
from datetime import UTC, datetime

from loguru import logger
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobModel, JobStatus, JobType
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.services.base import BaseService
from app.services.exceptions.jobs import InvalidJobError, JobNotFoundError, JobStateConflictError
from app.services.exceptions.projects import ProjectNotFoundError


class JobService(BaseService[JobCRUDRepository]):
    """Бизнес-логика очереди фоновых задач."""

    repository_class = JobCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)

    async def get_job_by_id(self, job_id: int) -> JobModel:
        """Возвращает фоновую задачу по ID."""

        job = await self.repository.get_obj_by_id(obj_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        return job

    async def enqueue_job(
        self,
        project_id: int,
        job_type: JobType,
        input_data: dict[str, JsonValue],
        project_file_id: int | None = None,
    ) -> JobModel:
        """Ставит фоновую задачу с неизменяемым снимком входов в очередь."""

        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        if project_file_id is not None:
            project_file = await self.project_file_repository.get_obj_by_id(obj_id=project_file_id)
            if project_file is None:
                raise InvalidJobError(f'Project file with id={project_file_id} not found')
            if project_file.project_id != project_id:
                raise InvalidJobError(
                    f'Project file with id={project_file_id} does not belong to project id={project_id}'
                )

        job = await self.repository.create_obj(
            new_obj=JobModel(
                project_id=project_id,
                project_file_id=project_file_id,
                type=job_type,
                status=JobStatus.QUEUED,
                input_data=deepcopy(input_data),
            )
        )
        await self.session.commit()
        logger.info('Задача поставлена в очередь: id={}, type={}, project_id={}', job.id, job.type, project_id)
        return job

    async def claim_next_job(self) -> JobModel | None:
        """Захватывает следующую задачу для обработки worker."""

        job = await self.repository.claim_next_queued()
        await self.session.commit()
        if job is not None:
            logger.info('Задача запущена: id={}, type={}', job.id, job.type)
        return job

    async def update_stage(self, job_id: int, stage: str) -> JobModel:
        """Обновляет этап выполняющейся задачи."""

        self._validate_stage(stage=stage)
        job = await self._get_running_job_for_update(job_id=job_id)
        job.stage = stage
        await self.session.commit()
        return job

    async def succeed_job(self, job_id: int, result: dict[str, JsonValue]) -> JobModel:
        """Завершает выполняющуюся задачу успешно."""

        job = await self._get_running_job_for_update(job_id=job_id)
        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = deepcopy(result)
        job.error = None
        job.finished_at = self._utc_now()
        await self.session.commit()
        logger.info('Задача завершена: id={}, status={}', job.id, job.status)
        return job

    async def fail_job(self, job_id: int, error: str) -> JobModel:
        """Завершает выполняющуюся задачу ошибкой."""

        normalized_error = error.strip()
        if not normalized_error:
            raise InvalidJobError('Job error must not be empty')

        job = await self._get_running_job_for_update(job_id=job_id)
        job.status = JobStatus.FAILED
        job.stage = 'failed'
        job.error = normalized_error
        job.result = None
        job.finished_at = self._utc_now()
        await self.session.commit()
        logger.warning('Задача завершена с ошибкой: id={}', job.id)
        return job

    async def fail_interrupted_jobs(self) -> int:
        """Закрывает задачи, прерванные предыдущим запуском worker."""

        count = await self.repository.fail_interrupted(error='Worker stopped before the job completed')
        await self.session.commit()
        if count:
            logger.warning('Прерванные задачи закрыты с ошибкой: count={}', count)
        return count

    async def _get_running_job_for_update(self, job_id: int) -> JobModel:
        job = await self.repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        if job.status is not JobStatus.RUNNING:
            raise JobStateConflictError(job_id=job.id, status=job.status)
        return job

    @staticmethod
    def _validate_stage(stage: str) -> None:
        if not stage.strip() or len(stage) > 100:
            raise InvalidJobError('Job stage must contain from 1 to 100 characters')

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)
