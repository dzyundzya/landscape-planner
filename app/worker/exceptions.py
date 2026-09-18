class WorkerError(Exception):
    """Базовая ошибка процесса фоновых задач."""


class WorkerLockLostError(WorkerError):
    """Worker потерял сессию, удерживающую PostgreSQL advisory lock."""


class UnsupportedJobTypeError(WorkerError):
    """Для типа задачи не зарегистрирован обработчик."""
