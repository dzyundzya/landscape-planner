class AppError(Exception):
    """Базовая ошибка приложения."""


class NotFoundError(AppError):
    """Сущность не найдена."""

    def __init__(self, entity: str, obj_id: int) -> None:
        super().__init__(f'Объект «{entity}» с id={obj_id} не найден')


class AlreadyExistsError(AppError):
    """Сущность уже существует."""

    def __init__(self, entity: str, field: str, value: str) -> None:
        super().__init__(f'Объект «{entity}» с {field}={value} уже существует')


class BadRequestError(AppError):
    """Некорректный запрос."""
