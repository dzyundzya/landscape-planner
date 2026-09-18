from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import BinaryIO

from anyio import to_thread
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.manager import settings
from app.models import FileArtifactFormat, FileArtifactKind, FileArtifactModel, JobStatus
from app.repositories.crud.file_artifacts import FileArtifactCRUDRepository
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.services.base import BaseService
from app.services.exceptions.file_artifacts import (
    FileArtifactAlreadyExistsError,
    FileArtifactNotFoundError,
    FileArtifactTooLargeError,
    FileArtifactUnavailableError,
    InvalidFileArtifactError,
)
from app.services.exceptions.jobs import JobNotFoundError, JobStateConflictError
from app.services.exceptions.projects import ProjectNotFoundError
from app.storage import LocalFileStorage, StoredFile
from app.storage.exceptions import EmptyStorageFileError, StorageFileTooLargeError

ARTIFACT_FORMATS = {
    FileArtifactKind.CANONICAL_DXF: FileArtifactFormat.DXF,
    FileArtifactKind.RESULT_DXF: FileArtifactFormat.DXF,
    FileArtifactKind.PLAN_JSON: FileArtifactFormat.JSON,
    FileArtifactKind.REPORT_JSON: FileArtifactFormat.JSON,
    FileArtifactKind.REPORT_MARKDOWN: FileArtifactFormat.MARKDOWN,
}
DEFAULT_DOWNLOAD_NAMES = {
    FileArtifactKind.CANONICAL_DXF: 'canonical.dxf',
    FileArtifactKind.RESULT_DXF: 'result.dxf',
    FileArtifactKind.PLAN_JSON: 'plan.json',
    FileArtifactKind.REPORT_JSON: 'report.json',
    FileArtifactKind.REPORT_MARKDOWN: 'report.md',
}
CONTENT_TYPES = {
    FileArtifactFormat.DXF: 'application/dxf',
    FileArtifactFormat.JSON: 'application/json',
    FileArtifactFormat.MARKDOWN: 'text/markdown; charset=utf-8',
}
ALLOWED_SUFFIXES = {
    FileArtifactFormat.DXF: {'.dxf'},
    FileArtifactFormat.JSON: {'.json'},
    FileArtifactFormat.MARKDOWN: {'.md', '.markdown'},
}


@dataclass(frozen=True, slots=True)
class FileArtifactDownload:
    """Данные для безопасной выдачи сформированного файла."""

    path: Path
    download_name: str
    content_type: str


class FileArtifactService(BaseService[FileArtifactCRUDRepository]):
    """Бизнес-логика сформированных файлов проекта."""

    repository_class = FileArtifactCRUDRepository

    def __init__(self, async_session: AsyncSession, storage: LocalFileStorage | None = None) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.job_repository = JobCRUDRepository(async_session=async_session)
        self.storage = storage or LocalFileStorage(
            root=settings.FILE_STORAGE_ROOT,
            max_size_bytes=settings.MAX_ARTIFACT_SIZE_BYTES,
        )

    async def create_artifact(
        self,
        project_id: int,
        job_id: int,
        kind: FileArtifactKind,
        source: BinaryIO,
        project_file_id: int | None = None,
        download_name: str | None = None,
        *,
        commit: bool = True,
    ) -> FileArtifactModel:
        """Атомарно публикует неизменяемый файл, сформированный worker."""

        file_format = ARTIFACT_FORMATS[kind]
        safe_download_name = self._get_download_name(kind=kind, download_name=download_name)
        stored_file = await self._save_file(project_id=project_id, file_format=file_format, source=source)

        try:
            await self._validate_relations(
                project_id=project_id,
                project_file_id=project_file_id,
                job_id=job_id,
                kind=kind,
            )
            artifact = await self.repository.create_obj(
                new_obj=FileArtifactModel(
                    project_id=project_id,
                    project_file_id=project_file_id,
                    job_id=job_id,
                    kind=kind,
                    format=file_format,
                    download_name=safe_download_name,
                    storage_key=stored_file.storage_key,
                    content_type=CONTENT_TYPES[file_format],
                    size_bytes=stored_file.size_bytes,
                    sha256=stored_file.sha256,
                )
            )
            if commit:
                await self.session.commit()
        except Exception:
            await to_thread.run_sync(self.storage.delete, stored_file.storage_key)
            raise

        logger.info(
            'Файл результата опубликован: artifact_id={}, project_id={}, job_id={}, kind={}',
            artifact.id,
            project_id,
            job_id,
            artifact.kind,
        )
        return artifact

    async def get_download(self, project_id: int, artifact_id: int) -> FileArtifactDownload:
        """Возвращает проверенные данные для скачивания файла проекта."""

        artifact = await self.repository.get_artifact_for_project(
            artifact_id=artifact_id,
            project_id=project_id,
        )
        if artifact is None:
            raise FileArtifactNotFoundError(artifact_id=artifact_id)

        path = self.storage.get_path(storage_key=artifact.storage_key)
        if not path.is_file():
            raise FileArtifactUnavailableError(artifact_id=artifact.id)

        return FileArtifactDownload(
            path=path,
            download_name=artifact.download_name,
            content_type=artifact.content_type,
        )

    async def _validate_relations(
        self,
        project_id: int,
        project_file_id: int | None,
        job_id: int,
        kind: FileArtifactKind,
    ) -> None:
        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        job = await self.job_repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        if job.project_id != project_id:
            raise InvalidFileArtifactError(f'Задача с id={job_id} не принадлежит проекту с id={project_id}')
        if job.status is not JobStatus.RUNNING:
            raise JobStateConflictError(job_id=job.id, status=job.status)
        if await self.repository.get_artifact_by_job_and_kind(job_id=job_id, kind=kind) is not None:
            raise FileArtifactAlreadyExistsError(job_id=job_id, kind=kind)

        if project_file_id is not None:
            project_file = await self.project_file_repository.get_obj_by_id(obj_id=project_file_id)
            if project_file is None:
                raise InvalidFileArtifactError(f'Исходный файл с id={project_file_id} не найден')
            if project_file.project_id != project_id:
                raise InvalidFileArtifactError(
                    f'Исходный файл с id={project_file_id} не принадлежит проекту с id={project_id}'
                )

    async def _save_file(
        self,
        project_id: int,
        file_format: FileArtifactFormat,
        source: BinaryIO,
    ) -> StoredFile:
        try:
            return await to_thread.run_sync(
                partial(
                    self.storage.save_artifact,
                    project_id=project_id,
                    file_format=file_format,
                    source=source,
                )
            )
        except StorageFileTooLargeError as exc:
            raise FileArtifactTooLargeError(max_size_bytes=exc.max_size_bytes) from exc
        except EmptyStorageFileError as exc:
            raise InvalidFileArtifactError('Файл артефакта пуст') from exc

    @staticmethod
    def _get_download_name(kind: FileArtifactKind, download_name: str | None) -> str:
        name = download_name or DEFAULT_DOWNLOAD_NAMES[kind]
        safe_name = Path(name.replace('\\', '/')).name.strip()
        file_format = ARTIFACT_FORMATS[kind]
        if not safe_name or '\x00' in safe_name or len(safe_name) > 255:
            raise InvalidFileArtifactError('Некорректное имя файла артефакта для скачивания')
        if Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES[file_format]:
            raise InvalidFileArtifactError(f'Имя файла артефакта должно соответствовать формату {file_format.value}')
        return safe_name
