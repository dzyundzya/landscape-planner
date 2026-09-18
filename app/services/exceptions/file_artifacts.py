from app.models import FileArtifactKind
from app.services.exceptions.base import AlreadyExistsError, AppError, NotFoundError


class FileArtifactNotFoundError(NotFoundError):
    """Сформированный файл проекта не найден."""

    def __init__(self, artifact_id: int) -> None:
        super().__init__(entity='файловый артефакт', obj_id=artifact_id)


class InvalidFileArtifactError(AppError):
    """Параметры сформированного файла некорректны."""


class FileArtifactTooLargeError(AppError):
    """Сформированный файл превышает допустимый размер."""

    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(f'Размер артефакта превышает {max_size_bytes} байт')


class FileArtifactUnavailableError(AppError):
    """Файл результата зарегистрирован, но недоступен в хранилище."""

    def __init__(self, artifact_id: int) -> None:
        super().__init__(f'Файловый артефакт с id={artifact_id} недоступен')


class FileArtifactAlreadyExistsError(AlreadyExistsError):
    """Задача уже сформировала файл указанного вида."""

    def __init__(self, job_id: int, kind: FileArtifactKind) -> None:
        super().__init__(entity='файловый артефакт', field='job_id/kind', value=f'{job_id}/{kind.value}')
