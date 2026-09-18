from unittest.mock import AsyncMock

import pytest

from app.models import JobModel, JobType
from app.worker.dispatcher import JobDispatcher
from app.worker.exceptions import UnsupportedJobTypeError


async def test_dispatcher_calls_registered_handler() -> None:
    """Проверяет передачу задачи обработчику зарегистрированного типа."""

    handler = AsyncMock()
    guard = AsyncMock()
    job = JobModel(type=JobType.ANALYZE)
    dispatcher = JobDispatcher({JobType.ANALYZE: handler})

    await dispatcher.execute(job=job, ensure_ownership=guard)

    assert dispatcher.job_types == (JobType.ANALYZE,)
    handler.execute.assert_awaited_once_with(job=job, ensure_ownership=guard)


async def test_dispatcher_rejects_unsupported_job_type() -> None:
    """Проверяет явную ошибку при отсутствии обработчика типа задачи."""

    dispatcher = JobDispatcher()

    with pytest.raises(UnsupportedJobTypeError, match='generate_plan'):
        await dispatcher.execute(
            job=JobModel(type=JobType.GENERATE_PLAN),
            ensure_ownership=AsyncMock(),
        )
