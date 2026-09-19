import asyncio
from contextlib import suppress
from enum import StrEnum

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import JobModel, JobStatus
from app.services.exceptions.jobs import JobStateConflictError
from app.services.jobs import JobService
from app.worker.dispatcher import JobDispatcher
from app.worker.exceptions import WorkerLockLostError
from app.worker.lock import WorkerAdvisoryLock


class WorkerExitReason(StrEnum):
    """Причина штатного завершения цикла worker."""

    STOPPED = 'stopped'
    ALREADY_RUNNING = 'already_running'
    LOCK_LOST = 'lock_lost'


class WorkerRunner:
    """Последовательно выполняет поддерживаемые задачи под advisory lock."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        dispatcher: JobDispatcher,
        advisory_lock: WorkerAdvisoryLock,
        poll_interval_seconds: float = 1.0,
        lock_check_interval_seconds: float = 1.0,
    ) -> None:
        if poll_interval_seconds <= 0 or lock_check_interval_seconds <= 0:
            raise ValueError('Интервалы worker должны быть положительными')
        self.session_factory = session_factory
        self.dispatcher = dispatcher
        self.advisory_lock = advisory_lock
        self.poll_interval_seconds = poll_interval_seconds
        self.lock_check_interval_seconds = lock_check_interval_seconds

    async def run(self, stop_event: asyncio.Event | None = None) -> WorkerExitReason:
        """Получает единоличный lock, восстанавливает очередь и запускает цикл."""

        stop = stop_event or asyncio.Event()
        if not await self.advisory_lock.acquire():
            logger.warning('Воркер уже запущен другим процессом')
            return WorkerExitReason.ALREADY_RUNNING

        try:
            await self._ensure_lock()
            await self._fail_interrupted_jobs()
            while not stop.is_set():
                await self._ensure_lock()
                job = await self._claim_next_job()
                if job is None:
                    await self._wait_for_work(stop=stop)
                    continue
                if not await self._process_job(job=job):
                    return WorkerExitReason.LOCK_LOST
            return WorkerExitReason.STOPPED
        except WorkerLockLostError:
            logger.error('Воркер остановлен после потери advisory-блокировки')
            return WorkerExitReason.LOCK_LOST
        finally:
            await self.advisory_lock.release()

    async def _claim_next_job(self) -> JobModel | None:
        async with self.session_factory() as session:
            return await JobService(async_session=session).claim_next_job(job_types=self.dispatcher.job_types)

    async def _fail_interrupted_jobs(self) -> None:
        async with self.session_factory() as session:
            await JobService(async_session=session).fail_interrupted_jobs()

    async def _process_job(self, job: JobModel) -> bool:
        try:
            await self._execute_with_lock_monitor(job=job)
            await self._ensure_lock()
            await self._fail_if_still_running(job_id=job.id)
        except WorkerLockLostError:
            return False
        except Exception as exc:
            logger.exception('Обработчик фоновой задачи завершился ошибкой: job_id={}, type={}', job.id, job.type)
            try:
                await self._ensure_lock()
                await self._fail_job(job_id=job.id, error=self._format_error(exc))
            except WorkerLockLostError:
                return False
        return True

    async def _execute_with_lock_monitor(self, job: JobModel) -> None:
        task = asyncio.create_task(
            self.dispatcher.execute(job=job, ensure_ownership=self._ensure_lock),
            name=f'job-{job.id}',
        )
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self.lock_check_interval_seconds)
                if done:
                    break
                await self._ensure_lock()
            await task
        except WorkerLockLostError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise

    async def _fail_if_still_running(self, job_id: int) -> None:
        async with self.session_factory() as session:
            service = JobService(async_session=session)
            job = await service.get_job_by_id(job_id=job_id)
            if job.status is JobStatus.RUNNING:
                await service.fail_job(
                    job_id=job.id,
                    error='Обработчик воркера завершился, не завершив задачу',
                )

    async def _fail_job(self, job_id: int, error: str) -> None:
        async with self.session_factory() as session:
            try:
                await JobService(async_session=session).fail_job(job_id=job_id, error=error)
            except JobStateConflictError:
                logger.warning('Не удалось пометить задачу ошибочной: её состояние уже изменилось, job_id={}', job_id)

    async def _ensure_lock(self) -> None:
        try:
            await self.advisory_lock.ensure_owned()
        except Exception as exc:
            raise WorkerLockLostError(str(exc)) from exc

    async def _wait_for_work(self, stop: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_seconds)
        except TimeoutError:
            return

    @staticmethod
    def _format_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return f'{exc.__class__.__name__}: {message}'[:4000]
