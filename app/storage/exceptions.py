class StorageError(Exception):
    """Базовая ошибка файлового хранилища."""


class StorageFileTooLargeError(StorageError):
    """Размер файла превышает установленный предел."""

    def __init__(self, max_size_bytes: int) -> None:
        self.max_size_bytes = max_size_bytes
        super().__init__(f'Размер файла превышает {max_size_bytes} байт')


class EmptyStorageFileError(StorageError):
    """Загруженный файл не содержит данных."""

    def __init__(self) -> None:
        super().__init__('Файл в хранилище не содержит данных')
