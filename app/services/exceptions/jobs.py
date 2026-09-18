from app.models import JobStatus
from app.services.exceptions.base import AppError, NotFoundError


class JobNotFoundError(NotFoundError):
    """Фоновая задача не найдена."""

    def __init__(self, job_id: int) -> None:
        super().__init__(entity='фоновая задача', obj_id=job_id)


class InvalidJobError(AppError):
    """Параметры фоновой задачи некорректны."""


class JobStateConflictError(AppError):
    """Переход состояния фоновой задачи запрещён."""

    def __init__(self, job_id: int, status: JobStatus) -> None:
        super().__init__(f'Задачу с id={job_id} нельзя изменить из состояния {status.value}')
