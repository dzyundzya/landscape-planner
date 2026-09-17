import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, JobType, ProjectModel
from app.services.exceptions.jobs import JobStateConflictError
from app.services.exceptions.projects import ProjectNotFoundError
from app.services.jobs import JobService


async def test_job_success_lifecycle(db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет полный успешный переход задачи через состояния очереди."""

    service = JobService(async_session=db_session)
    job = await service.enqueue_job(
        project_id=project.id,
        job_type=JobType.ANALYZE,
        project_file_id=None,
        input_data={'source_file_id': 10},
    )

    claimed_job = await service.claim_next_job()
    assert claimed_job is not None
    assert claimed_job.id == job.id
    assert claimed_job.status is JobStatus.RUNNING
    assert claimed_job.stage == 'starting'
    assert claimed_job.started_at is not None

    updated_job = await service.update_stage(job_id=job.id, stage='reading_entities')
    assert updated_job.stage == 'reading_entities'

    completed_job = await service.succeed_job(job_id=job.id, result={'entities_count': 42})
    assert completed_job.status is JobStatus.SUCCEEDED
    assert completed_job.stage == 'completed'
    assert completed_job.result == {'entities_count': 42}
    assert completed_job.error is None
    assert completed_job.finished_at is not None


async def test_job_failure_blocks_second_completion(db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет ошибочное завершение и запрет повторного перехода состояния."""

    service = JobService(async_session=db_session)
    job = await service.enqueue_job(
        project_id=project.id,
        job_type=JobType.EXPORT,
        project_file_id=None,
        input_data={'plan_id': 15, 'revision': 2},
    )
    await service.claim_next_job()

    failed_job = await service.fail_job(job_id=job.id, error='Export failed')
    assert failed_job.status is JobStatus.FAILED
    assert failed_job.stage == 'failed'
    assert failed_job.error == 'Export failed'
    assert failed_job.result is None
    assert failed_job.finished_at is not None

    with pytest.raises(JobStateConflictError):
        await service.succeed_job(job_id=job.id, result={})


async def test_claim_job_preserves_queue_order(db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет захват задач в порядке создания и идентификатора."""

    service = JobService(async_session=db_session)
    first_job = await service.enqueue_job(
        project_id=project.id,
        job_type=JobType.CONVERT_DWF,
        project_file_id=None,
        input_data={},
    )
    await service.enqueue_job(
        project_id=project.id,
        job_type=JobType.ANALYZE,
        project_file_id=None,
        input_data={},
    )

    claimed_job = await service.claim_next_job()

    assert claimed_job is not None
    assert claimed_job.id == first_job.id


async def test_interrupted_jobs_are_failed(db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет восстановление очереди после прерывания worker."""

    service = JobService(async_session=db_session)
    job = await service.enqueue_job(
        project_id=project.id,
        job_type=JobType.GENERATE_PLAN,
        project_file_id=None,
        input_data={},
    )
    await service.claim_next_job()

    count = await service.fail_interrupted_jobs()
    recovered_job = await service.get_job_by_id(job_id=job.id)

    assert count == 1
    assert recovered_job.status is JobStatus.FAILED
    assert recovered_job.stage == 'interrupted'
    assert recovered_job.error == 'Worker stopped before the job completed'
    assert recovered_job.finished_at is not None


async def test_enqueue_job_requires_existing_project(db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет запрет постановки задачи для отсутствующего проекта."""

    service = JobService(async_session=db_session)

    with pytest.raises(ProjectNotFoundError):
        await service.enqueue_job(
            project_id=project.id + 1000,
            job_type=JobType.ANALYZE,
            project_file_id=None,
            input_data={},
        )
