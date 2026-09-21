from app.services.exceptions.base import AppError


class AgentUnavailableError(AppError):
    """Агент отключён или его модель не настроена."""


class AgentExecutionError(AppError):
    """Модель или цикл агента не смогли обработать запрос."""
