import asyncio
import signal
from contextlib import suppress

from loguru import logger

from app.core.config.logger import configure_logger
from app.core.config.manager import settings
from app.core.db.database import async_db
from app.worker.dispatcher import JobDispatcher
from app.worker.lock import WorkerAdvisoryLock
from app.worker.runner import WorkerExitReason, WorkerRunner


def build_dispatcher() -> JobDispatcher:
    """Создаёт registry реализованных обработчиков фоновых задач."""

    return JobDispatcher()


async def run_worker() -> WorkerExitReason:
    """Настраивает сигналы и запускает единственный локальный worker."""

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):  # pragma: no cover
            loop.add_signal_handler(signum, stop_event.set)

    runner = WorkerRunner(
        session_factory=async_db.async_session_maker,
        dispatcher=build_dispatcher(),
        advisory_lock=WorkerAdvisoryLock(
            engine=async_db.async_engine,
            lock_id=settings.WORKER_ADVISORY_LOCK_ID,
        ),
        poll_interval_seconds=settings.WORKER_POLL_INTERVAL_SECONDS,
        lock_check_interval_seconds=settings.WORKER_LOCK_CHECK_INTERVAL_SECONDS,
    )
    logger.info('Worker Landscape planner запускается')
    try:
        return await runner.run(stop_event=stop_event)
    finally:
        await async_db.dispose()
        logger.info('Worker Landscape planner остановлен')


def main() -> None:
    """CLI entrypoint для `python -m app.worker`."""

    configure_logger()
    reason = asyncio.run(run_worker())
    if reason is WorkerExitReason.LOCK_LOST:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
