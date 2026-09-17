from app.services.exceptions.base import AppError


class InvalidProjectFileError(AppError):
    """Исходный файл имеет неподдерживаемый формат или повреждён."""


class ProjectFileTooLargeError(AppError):
    """Исходный файл превышает допустимый размер."""

    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(f'File size exceeds {max_size_bytes} bytes')
