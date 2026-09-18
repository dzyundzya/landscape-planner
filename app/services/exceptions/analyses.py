from app.services.exceptions.base import AppError, NotFoundError


class AnalysisNotFoundError(NotFoundError):
    """Анализ текущего исходника проекта не найден."""

    def __init__(self, project_id: int) -> None:
        super().__init__(entity='анализ проекта', obj_id=project_id)


class AnalysisSourceNotReadyError(AppError):
    """Текущий исходник проекта нельзя передать анализатору."""


class InvalidAnalysisError(AppError):
    """Результат анализа не соответствует поставленной задаче."""
