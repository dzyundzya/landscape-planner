from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models import JobModel, JobStatus
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class JobCRUDRepository(BaseCRUDRepository[JobModel]):
    """Операции с очередью фоновых задач."""

    model = JobModel

    async def get_job_by_id_for_update(self, job_id: int) -> JobModel | None:
        """Получает задачу с блокировкой до завершения транзакции."""

        return await self.session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())

    async def claim_next_queued(self) -> JobModel | None:
        """Атомарно захватывает следующую задачу очереди."""

        job = await self.session.scalar(
            select(JobModel)
            .where(JobModel.status == JobStatus.QUEUED)
            .order_by(JobModel.created_at, JobModel.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None

        job.status = JobStatus.RUNNING
        job.stage = 'starting'
        job.started_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def fail_interrupted(self, error: str) -> int:
        """Помечает незавершённые задачи ошибкой после перезапуска worker."""

        result = await self.session.execute(
            update(JobModel)
            .where(JobModel.status == JobStatus.RUNNING)
            .values(
                status=JobStatus.FAILED,
                stage='interrupted',
                error=error,
                finished_at=datetime.now(UTC),
            )
            .returning(JobModel.id)
        )
        return len(result.scalars().all())
