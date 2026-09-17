import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.models.enums import ProjectFileFormat
from app.storage.exceptions import EmptyStorageFileError, StorageFileTooLargeError

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Метаданные сохранённого файла."""

    storage_key: str
    path: Path
    size_bytes: int
    sha256: str


class LocalFileStorage:
    """Сохраняет файлы под внутренними именами в локальной директории."""

    def __init__(self, root: Path, max_size_bytes: int) -> None:
        self.root = root.resolve()
        self.max_size_bytes = max_size_bytes

    def save_source(
        self,
        project_id: int,
        file_format: ProjectFileFormat,
        source: BinaryIO,
    ) -> StoredFile:
        """Атомарно сохраняет исходный файл проекта."""

        file_id = uuid4().hex
        storage_key = f'projects/{project_id}/sources/{file_id}.{file_format.value}'
        destination = self._resolve(storage_key)
        temporary = self._resolve(f'.tmp/{file_id}.part')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size_bytes = 0

        try:
            source.seek(0)
            with temporary.open('xb') as target:
                for chunk in self._read_chunks(source):
                    size_bytes += len(chunk)
                    if size_bytes > self.max_size_bytes:
                        raise StorageFileTooLargeError(max_size_bytes=self.max_size_bytes)

                    digest.update(chunk)
                    target.write(chunk)

            if size_bytes == 0:
                raise EmptyStorageFileError

            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return StoredFile(
            storage_key=storage_key,
            path=destination,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    def delete(self, storage_key: str) -> None:
        """Удаляет файл по внутреннему ключу."""

        self._resolve(storage_key).unlink(missing_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Storage key points outside storage root')
        return path

    @staticmethod
    def _read_chunks(source: BinaryIO) -> Iterator[bytes]:
        while chunk := source.read(CHUNK_SIZE):
            yield chunk
