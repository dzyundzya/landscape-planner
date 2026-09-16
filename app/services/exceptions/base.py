class AppError(Exception):
    """Базовая ошибка приложения."""


class NotFoundError(AppError):
    """Сущность не найдена."""

    def __init__(self, entity: str, obj_id: int) -> None:
        super().__init__(f'{entity} with id={obj_id} not found')


class AlreadyExistsError(AppError):
    """Сущность уже существует."""

    def __init__(self, entity: str, field: str, value: str) -> None:
        super().__init__(f'{entity} with {field}={value} already exists')


class BadRequestError(AppError):
    """Некорректный запрос."""
