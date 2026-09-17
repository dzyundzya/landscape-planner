class StorageError(Exception):
    """Базовая ошибка файлового хранилища."""


class StorageFileTooLargeError(StorageError):
    """Размер файла превышает установленный предел."""

    def __init__(self, max_size_bytes: int) -> None:
        self.max_size_bytes = max_size_bytes
        super().__init__(f'File size exceeds {max_size_bytes} bytes')


class EmptyStorageFileError(StorageError):
    """Загруженный файл не содержит данных."""
