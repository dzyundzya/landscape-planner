from app.services.exceptions.base import AppError, NotFoundError


class ProjectFileNotFoundError(NotFoundError):
    """Исходный файл проекта не найден."""

    def __init__(self, project_id: int) -> None:
        super().__init__(entity='исходный файл проекта', obj_id=project_id)


class InvalidProjectFileError(AppError):
    """Исходный файл имеет неподдерживаемый формат или повреждён."""


class ProjectFileTooLargeError(AppError):
    """Исходный файл превышает допустимый размер."""

    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(f'Размер файла превышает {max_size_bytes} байт')
