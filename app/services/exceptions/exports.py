from app.services.exceptions.base import AppError, NotFoundError


class ExportNotFoundError(NotFoundError):
    """Комплект экспорта не найден внутри плана."""

    def __init__(self, export_id: int) -> None:
        super().__init__(entity='Export', obj_id=export_id)


class ExportPrerequisiteError(AppError):
    """Ревизия плана ещё не готова к проверенному экспорту."""


class InvalidExportError(AppError):
    """Результаты задачи не образуют корректный комплект экспорта."""
