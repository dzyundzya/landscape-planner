from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models import JobModel, JobStatus, JobType
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class JobCRUDRepository(BaseCRUDRepository[JobModel]):
    """Операции с очередью фоновых задач."""

    model = JobModel

    async def get_active_analysis(self, project_file_id: int) -> JobModel | None:
        """Возвращает незавершённую задачу анализа исходника."""

        return await self.session.scalar(
            select(JobModel)
            .where(
                JobModel.project_file_id == project_file_id,
                JobModel.type == JobType.ANALYZE,
                JobModel.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
            )
            .order_by(JobModel.created_at, JobModel.id)
            .limit(1)
        )

    async def get_active_plan_generation(self, project_id: int, config_snapshot_id: int) -> JobModel | None:
        """Возвращает незавершённую генерацию для снимка конфигурации."""

        return await self.session.scalar(
            select(JobModel)
            .where(
                JobModel.project_id == project_id,
                JobModel.type == JobType.GENERATE_PLAN,
                JobModel.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
                JobModel.input_data['config_snapshot_id'].as_integer() == config_snapshot_id,
            )
            .order_by(JobModel.created_at, JobModel.id)
            .limit(1)
        )

    async def get_active_export(self, plan_id: int, plan_revision: int) -> JobModel | None:
        """Возвращает незавершённый экспорт конкретной ревизии плана."""

        return await self.session.scalar(
            select(JobModel)
            .where(
                JobModel.type == JobType.EXPORT,
                JobModel.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
                JobModel.input_data['plan_id'].as_integer() == plan_id,
                JobModel.input_data['plan_revision'].as_integer() == plan_revision,
            )
            .order_by(JobModel.created_at, JobModel.id)
            .limit(1)
        )

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
