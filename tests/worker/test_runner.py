import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models import JobModel, JobStatus, JobType, ProjectModel
from app.services.jobs import JobService
from app.worker.dispatcher import JobDispatcher, OwnershipGuard
from app.worker.lock import WorkerAdvisoryLock
from app.worker.runner import WorkerExitReason, WorkerRunner

TEST_LOCK_ID = 1_196_578_127


class CompletingHandler:
    """Тестовый обработчик, атомарно завершающий задачу."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        stop_event: asyncio.Event,
    ) -> None:
        self.session_factory = session_factory
        self.stop_event = stop_event

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        await ensure_ownership()
        async with self.session_factory() as session:
            await JobService(async_session=session).succeed_job(
                job_id=job.id,
                result={'handled': job.type.value},
            )
        self.stop_event.set()


class FailingHandler:
    """Тестовый обработчик с управляемой ошибкой."""

    def __init__(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        self.stop_event.set()
        raise ValueError('synthetic handler failure')


class BlockingHandler:
    """Тестовый обработчик для имитации потери lock во время расчёта."""

    def __init__(self, started: asyncio.Event, proceed: asyncio.Event) -> None:
        self.started = started
        self.proceed = proceed

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        self.started.set()
        await self.proceed.wait()
        await ensure_ownership()


class IncompleteHandler:
    """Тестовый обработчик, нарушающий контракт завершения Job."""

    def __init__(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        await ensure_ownership()
        self.stop_event.set()


def make_runner(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    dispatcher: JobDispatcher,
    advisory_lock: WorkerAdvisoryLock | None = None,
) -> WorkerRunner:
    """Создаёт быстрый worker для интеграционных тестов."""

    return WorkerRunner(
        session_factory=test_sessionmaker,
        dispatcher=dispatcher,
        advisory_lock=advisory_lock or WorkerAdvisoryLock(test_engine, TEST_LOCK_ID),
        poll_interval_seconds=0.01,
        lock_check_interval_seconds=0.01,
    )


async def enqueue_job(db_session: AsyncSession, project_id: int, job_type: JobType) -> JobModel:
    """Ставит простую задачу в тестовую очередь."""

    return await JobService(async_session=db_session).enqueue_job(
        project_id=project_id,
        job_type=job_type,
        input_data={},
    )


async def test_worker_processes_only_supported_job_types(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет выбор поддерживаемой задачи без захвата неподдерживаемой."""

    unsupported = await enqueue_job(db_session, project.id, JobType.CONVERT_DWF)
    supported = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    stop_event = asyncio.Event()
    runner = make_runner(
        test_engine,
        test_sessionmaker,
        JobDispatcher({JobType.ANALYZE: CompletingHandler(test_sessionmaker, stop_event)}),
    )

    reason = await runner.run(stop_event=stop_event)
    await db_session.refresh(unsupported)
    await db_session.refresh(supported)

    assert reason is WorkerExitReason.STOPPED
    assert unsupported.status is JobStatus.QUEUED
    assert supported.status is JobStatus.SUCCEEDED
    assert supported.result == {'handled': 'analyze'}


async def test_second_worker_does_not_recover_running_jobs(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет отказ второго worker до изменения оставшихся running задач."""

    job = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    await JobService(db_session).claim_next_job()
    owner = WorkerAdvisoryLock(test_engine, TEST_LOCK_ID)
    assert await owner.acquire() is True
    try:
        runner = make_runner(test_engine, test_sessionmaker, JobDispatcher())
        reason = await runner.run(stop_event=asyncio.Event())
        await db_session.refresh(job)

        assert reason is WorkerExitReason.ALREADY_RUNNING
        assert job.status is JobStatus.RUNNING
    finally:
        await owner.release()


async def test_lock_owner_recovers_interrupted_jobs(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет восстановление running задач только после получения lock."""

    job = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    await JobService(db_session).claim_next_job()
    stop_event = asyncio.Event()
    stop_event.set()

    reason = await make_runner(test_engine, test_sessionmaker, JobDispatcher()).run(stop_event=stop_event)
    await db_session.refresh(job)

    assert reason is WorkerExitReason.STOPPED
    assert job.status is JobStatus.FAILED
    assert job.stage == 'interrupted'


async def test_handler_error_fails_job_and_keeps_worker_controlled(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет перевод задачи в failed после исключения обработчика."""

    job = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    stop_event = asyncio.Event()
    runner = make_runner(
        test_engine,
        test_sessionmaker,
        JobDispatcher({JobType.ANALYZE: FailingHandler(stop_event)}),
    )

    reason = await runner.run(stop_event=stop_event)
    await db_session.refresh(job)

    assert reason is WorkerExitReason.STOPPED
    assert job.status is JobStatus.FAILED
    assert job.error == 'ValueError: synthetic handler failure'


async def test_incomplete_handler_is_failed_by_runner(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет защиту от обработчика, вернувшегося без завершения Job."""

    job = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    stop_event = asyncio.Event()
    runner = make_runner(
        test_engine,
        test_sessionmaker,
        JobDispatcher({JobType.ANALYZE: IncompleteHandler(stop_event)}),
    )

    reason = await runner.run(stop_event=stop_event)
    await db_session.refresh(job)

    assert reason is WorkerExitReason.STOPPED
    assert job.status is JobStatus.FAILED
    assert job.error == 'Worker handler returned without completing the job'


async def test_lock_loss_stops_worker_without_publishing_job_state(
    test_engine: AsyncEngine,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет остановку без публикации после потери advisory lock."""

    job = await enqueue_job(db_session, project.id, JobType.ANALYZE)
    started = asyncio.Event()
    proceed = asyncio.Event()
    advisory_lock = WorkerAdvisoryLock(test_engine, TEST_LOCK_ID)
    runner = make_runner(
        test_engine,
        test_sessionmaker,
        JobDispatcher({JobType.ANALYZE: BlockingHandler(started, proceed)}),
        advisory_lock=advisory_lock,
    )
    runner_task = asyncio.create_task(runner.run())
    await asyncio.wait_for(started.wait(), timeout=1)

    await advisory_lock.release()
    proceed.set()
    reason = await asyncio.wait_for(runner_task, timeout=1)
    await db_session.refresh(job)

    assert reason is WorkerExitReason.LOCK_LOST
    assert job.status is JobStatus.RUNNING
