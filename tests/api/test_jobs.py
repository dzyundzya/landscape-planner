from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobType, ProjectModel
from app.services.jobs import JobService


async def test_get_job(client: AsyncClient, db_session: AsyncSession, project: ProjectModel) -> None:
    """Проверяет получение состояния фоновой задачи по ID."""

    job = await JobService(async_session=db_session).enqueue_job(
        project_id=project.id,
        job_type=JobType.ANALYZE,
        project_file_id=None,
        input_data={'config_version': 1},
    )

    response = await client.get(f'/api/jobs/{job.id}')
    data = response.json()

    assert response.status_code == 200
    assert data['id'] == job.id
    assert data['project_id'] == project.id
    assert data['project_file_id'] is None
    assert data['type'] == 'analyze'
    assert data['status'] == 'queued'
    assert data['stage'] is None
    assert data['result'] is None
    assert data['error'] is None
    assert datetime.fromisoformat(data['created_at']) == job.created_at
    assert data['started_at'] is None
    assert data['finished_at'] is None
    assert 'input_data' not in data


async def test_get_missing_job_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет ответ 404 при запросе отсутствующей задачи."""

    job = await JobService(async_session=db_session).enqueue_job(
        project_id=project.id,
        job_type=JobType.ANALYZE,
        project_file_id=None,
        input_data={},
    )
    missing_job_id = job.id + 1000

    response = await client.get(f'/api/jobs/{missing_job_id}')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Job with id={missing_job_id} not found'}
