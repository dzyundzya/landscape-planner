from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from app.models import JobModel, JobType
from app.worker.exceptions import UnsupportedJobTypeError

OwnershipGuard = Callable[[], Awaitable[None]]


class JobHandler(Protocol):
    """Обработчик, который сам атомарно публикует результат и завершает Job."""

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        """Вычисляет результат и проверяет lock непосредственно перед публикацией."""


class JobDispatcher:
    """Выбирает обработчик по типу фоновой задачи."""

    def __init__(self, handlers: Mapping[JobType, JobHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    @property
    def job_types(self) -> tuple[JobType, ...]:
        """Возвращает типы задач, которые worker может безопасно забрать."""

        return tuple(self._handlers)

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        """Передаёт задачу зарегистрированному обработчику."""

        handler = self._handlers.get(job.type)
        if handler is None:
            raise UnsupportedJobTypeError(f'No worker handler registered for job type={job.type.value}')
        await handler.execute(job=job, ensure_ownership=ensure_ownership)
