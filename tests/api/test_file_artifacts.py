from io import BytesIO
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FileArtifactKind, JobType, ProjectModel
from app.services.file_artifacts import FileArtifactService
from app.services.jobs import JobService
from app.storage import LocalFileStorage


async def create_report_artifact(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> tuple[int, bytes]:
    """Создаёт файл отчёта для API-тестов."""

    job_service = JobService(async_session=db_session)
    job = await job_service.enqueue_job(
        project_id=project.id,
        job_type=JobType.EXPORT,
        input_data={'revision': 1},
    )
    await job_service.claim_next_job()
    content = b'{"status":"verified"}'
    artifact = await FileArtifactService(
        async_session=db_session,
        storage=LocalFileStorage(root=file_storage_root, max_size_bytes=1024 * 1024),
    ).create_artifact(
        project_id=project.id,
        job_id=job.id,
        kind=FileArtifactKind.REPORT_JSON,
        source=BytesIO(content),
    )
    return artifact.id, content


async def test_download_file_artifact(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет скачивание сформированного файла своего проекта."""

    artifact_id, content = await create_report_artifact(db_session, project, file_storage_root)

    response = await client.get(f'/api/projects/{project.id}/artifacts/{artifact_id}')

    assert response.status_code == 200
    assert response.content == content
    assert response.headers['content-type'] == 'application/json'
    assert 'filename="report.json"' in response.headers['content-disposition']


async def test_download_hides_artifact_from_another_project(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет запрет скачивания результата через ID другого проекта."""

    artifact_id, _ = await create_report_artifact(db_session, project, file_storage_root)

    response = await client.get(f'/api/projects/{project.id + 1000}/artifacts/{artifact_id}')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Объект «файловый артефакт» с id={artifact_id} не найден'}


async def test_download_reports_missing_storage_file(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет явную ошибку при потере зарегистрированного файла хранилищем."""

    artifact_id, _ = await create_report_artifact(db_session, project, file_storage_root)
    for path in (file_storage_root / 'projects' / str(project.id) / 'artifacts').iterdir():
        path.unlink()

    response = await client.get(f'/api/projects/{project.id}/artifacts/{artifact_id}')

    assert response.status_code == 409
    assert response.json() == {'detail': f'Файловый артефакт с id={artifact_id} недоступен'}
