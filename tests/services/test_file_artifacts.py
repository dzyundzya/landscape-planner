from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FileArtifactFormat, FileArtifactKind, JobType, ProjectModel
from app.services.exceptions.file_artifacts import (
    FileArtifactAlreadyExistsError,
    FileArtifactTooLargeError,
    InvalidFileArtifactError,
)
from app.services.exceptions.jobs import JobStateConflictError
from app.services.file_artifacts import FileArtifactService
from app.services.jobs import JobService
from app.storage import LocalFileStorage


def make_service(db_session: AsyncSession, root: Path, max_size_bytes: int = 1024) -> FileArtifactService:
    """Создаёт сервис с изолированным файловым хранилищем."""

    return FileArtifactService(
        async_session=db_session,
        storage=LocalFileStorage(root=root, max_size_bytes=max_size_bytes),
    )


async def create_running_job(db_session: AsyncSession, project_id: int):
    """Создаёт и захватывает задачу экспорта."""

    service = JobService(async_session=db_session)
    await service.enqueue_job(
        project_id=project_id,
        job_type=JobType.EXPORT,
        input_data={'revision': 1},
    )
    return await service.claim_next_job()


async def test_create_file_artifact(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет публикацию файла и сохранение его проверяемых метаданных."""

    job = await create_running_job(db_session=db_session, project_id=project.id)
    assert job is not None

    artifact = await make_service(db_session, file_storage_root).create_artifact(
        project_id=project.id,
        job_id=job.id,
        kind=FileArtifactKind.REPORT_MARKDOWN,
        source=BytesIO(b'# Report'),
        download_name='../../verification.md',
    )

    assert artifact.kind is FileArtifactKind.REPORT_MARKDOWN
    assert artifact.format is FileArtifactFormat.MARKDOWN
    assert artifact.download_name == 'verification.md'
    assert artifact.content_type == 'text/markdown; charset=utf-8'
    assert artifact.size_bytes == 8
    assert len(artifact.sha256) == 64
    assert (file_storage_root / artifact.storage_key).read_bytes() == b'# Report'


async def test_create_artifact_requires_running_job(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет запрет публикации результата для незапущенной задачи и очистку файла."""

    job = await JobService(async_session=db_session).enqueue_job(
        project_id=project.id,
        job_type=JobType.EXPORT,
        input_data={},
    )

    with pytest.raises(JobStateConflictError):
        await make_service(db_session, file_storage_root).create_artifact(
            project_id=project.id,
            job_id=job.id,
            kind=FileArtifactKind.RESULT_DXF,
            source=BytesIO(b'DXF result'),
        )

    assert not list(file_storage_root.rglob('*.dxf'))


async def test_create_artifact_rejects_duplicate_kind(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет единственность результата одного вида в рамках задачи."""

    job = await create_running_job(db_session=db_session, project_id=project.id)
    assert job is not None
    service = make_service(db_session, file_storage_root)
    await service.create_artifact(
        project_id=project.id,
        job_id=job.id,
        kind=FileArtifactKind.PLAN_JSON,
        source=BytesIO(b'{}'),
    )

    with pytest.raises(FileArtifactAlreadyExistsError):
        await service.create_artifact(
            project_id=project.id,
            job_id=job.id,
            kind=FileArtifactKind.PLAN_JSON,
            source=BytesIO(b'{"duplicate":true}'),
        )

    assert len(list(file_storage_root.rglob('*.json'))) == 1


async def test_create_artifact_rejects_invalid_name(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет соответствие расширения имени фактическому формату результата."""

    job = await create_running_job(db_session=db_session, project_id=project.id)
    assert job is not None

    with pytest.raises(InvalidFileArtifactError):
        await make_service(db_session, file_storage_root).create_artifact(
            project_id=project.id,
            job_id=job.id,
            kind=FileArtifactKind.REPORT_JSON,
            source=BytesIO(b'{}'),
            download_name='report.md',
        )


@pytest.mark.parametrize(
    ('content', 'exception_type'),
    [
        (b'', InvalidFileArtifactError),
        (b'too large', FileArtifactTooLargeError),
    ],
)
async def test_create_artifact_rejects_invalid_content(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
    content: bytes,
    exception_type: type[Exception],
) -> None:
    """Проверяет отклонение пустого результата и превышения допустимого размера."""

    job = await create_running_job(db_session=db_session, project_id=project.id)
    assert job is not None

    with pytest.raises(exception_type):
        await make_service(db_session, file_storage_root, max_size_bytes=4).create_artifact(
            project_id=project.id,
            job_id=job.id,
            kind=FileArtifactKind.REPORT_JSON,
            source=BytesIO(content),
        )
