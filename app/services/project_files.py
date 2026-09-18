from functools import partial
from pathlib import Path
from typing import BinaryIO

from anyio import to_thread
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.cad import InvalidDwfError, InvalidDxfError, validate_dwf, validate_dxf
from app.core.config.manager import settings
from app.models import ProjectFileFormat, ProjectFileModel, ProjectFileStatus
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.services.base import BaseService
from app.services.exceptions.project_files import InvalidProjectFileError, ProjectFileTooLargeError
from app.services.exceptions.projects import ProjectNotFoundError
from app.storage import LocalFileStorage, StoredFile
from app.storage.exceptions import EmptyStorageFileError, StorageFileTooLargeError


class ProjectFileService(BaseService[ProjectFileCRUDRepository]):
    """Бизнес-логика исходных файлов проектов."""

    repository_class = ProjectFileCRUDRepository

    def __init__(self, async_session: AsyncSession, storage: LocalFileStorage | None = None) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.storage = storage or LocalFileStorage(
            root=settings.FILE_STORAGE_ROOT,
            max_size_bytes=settings.MAX_UPLOAD_SIZE_BYTES,
        )

    async def upload_source_file(
        self,
        project_id: int,
        original_name: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> ProjectFileModel:
        """Сохраняет новый неизменяемый исходный файл проекта."""

        safe_original_name = self._sanitize_original_name(original_name=original_name)
        self._validate_content_type(content_type=content_type)
        file_format = self._get_file_format(original_name=safe_original_name)
        stored_file = await self._save_file(
            project_id=project_id,
            file_format=file_format,
            source=source,
        )

        try:
            await self._validate_file(file_format=file_format, path=stored_file.path)
            if await self.project_repository.get_project_by_id_for_update(project_id=project_id) is None:
                raise ProjectNotFoundError(project_id=project_id)

            version = await self.repository.get_next_version(project_id=project_id)
            project_file = await self.repository.create_obj(
                new_obj=ProjectFileModel(
                    project_id=project_id,
                    version=version,
                    format=file_format,
                    status=self._get_status(file_format=file_format),
                    original_name=safe_original_name,
                    storage_key=stored_file.storage_key,
                    content_type=content_type,
                    size_bytes=stored_file.size_bytes,
                    sha256=stored_file.sha256,
                )
            )
            await self.session.commit()
        except Exception:
            await to_thread.run_sync(self.storage.delete, stored_file.storage_key)
            raise

        logger.info(
            'Исходный файл загружен: project_id={}, file_id={}, format={}, version={}',
            project_id,
            project_file.id,
            project_file.format,
            project_file.version,
        )
        return project_file

    async def _save_file(
        self,
        project_id: int,
        file_format: ProjectFileFormat,
        source: BinaryIO,
    ) -> StoredFile:
        try:
            return await to_thread.run_sync(
                partial(
                    self.storage.save_source,
                    project_id=project_id,
                    file_format=file_format,
                    source=source,
                )
            )
        except StorageFileTooLargeError as exc:
            raise ProjectFileTooLargeError(max_size_bytes=exc.max_size_bytes) from exc
        except EmptyStorageFileError as exc:
            raise InvalidProjectFileError('Загруженный файл пуст') from exc

    @staticmethod
    async def _validate_file(file_format: ProjectFileFormat, path: Path) -> None:
        try:
            if file_format is ProjectFileFormat.DXF:
                await to_thread.run_sync(validate_dxf, path)
            else:
                await to_thread.run_sync(validate_dwf, path)
        except InvalidDxfError as exc:
            raise InvalidProjectFileError('Загруженный DXF-файл некорректен') from exc
        except InvalidDwfError as exc:
            raise InvalidProjectFileError('Загруженный DWF-файл некорректен') from exc

    @staticmethod
    def _get_file_format(original_name: str) -> ProjectFileFormat:
        suffix = Path(original_name).suffix.lower().removeprefix('.')
        try:
            return ProjectFileFormat(suffix)
        except ValueError as exc:
            raise InvalidProjectFileError('Поддерживаются только файлы DXF и DWF') from exc

    @staticmethod
    def _sanitize_original_name(original_name: str) -> str:
        safe_name = Path(original_name.replace('\\', '/')).name.strip()
        if not safe_name or '\x00' in safe_name or len(safe_name) > 255:
            raise InvalidProjectFileError('Некорректное имя исходного файла')
        return safe_name

    @staticmethod
    def _validate_content_type(content_type: str | None) -> None:
        if content_type is not None and len(content_type) > 100:
            raise InvalidProjectFileError('Некорректный тип содержимого исходного файла')

    @staticmethod
    def _get_status(file_format: ProjectFileFormat) -> ProjectFileStatus:
        if file_format is ProjectFileFormat.DXF:
            return ProjectFileStatus.READY
        return ProjectFileStatus.CONVERSION_REQUIRED
