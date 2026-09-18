from app.services.exceptions.base import AppError, NotFoundError


class ConfigSnapshotNotFoundError(NotFoundError):
    """Снимок настроек проекта не найден."""

    def __init__(self, project_id: int) -> None:
        super().__init__(entity='снимок конфигурации проекта', obj_id=project_id)


class ConfigPrerequisiteError(AppError):
    """Проект ещё не готов к подтверждению настроек."""


class InvalidConfigSnapshotError(AppError):
    """Настройки не согласованы с текущим анализом."""
