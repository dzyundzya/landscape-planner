from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectModel
from app.services.exports import ExportService
from app.services.jobs import JobService
from tests.services.test_exports import (
    create_verified_plan,
    publish_required_artifacts,
)


async def test_enqueue_and_get_export(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root,
) -> None:
    """Проверяет API от постановки проверенной ревизии до чтения комплекта."""

    plan_id, _ = await create_verified_plan(client=client, db_session=db_session, project=project)
    create_response = await client.post(
        f'/api/projects/{project.id}/plans/{plan_id}/exports',
        headers={'If-Match': '"1"'},
    )
    job = await JobService(async_session=db_session).claim_next_job()
    assert job is not None
    await publish_required_artifacts(
        db_session=db_session,
        project=project,
        job=job,
        file_storage_root=file_storage_root,
    )
    export = await ExportService(async_session=db_session).publish_export(
        job_id=job.id,
        export_version='dxf-export/1',
    )

    response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}/exports/{export.id}')
    data = response.json()

    assert create_response.status_code == 202
    assert create_response.json()['id'] == job.id
    assert response.status_code == 200
    assert data['id'] == export.id
    assert data['plan_revision'] == 1
    assert len(data['manifest']) == 4
    assert len(data['artifacts']) == 4
    assert all(item['export_id'] == export.id for item in data['artifacts'])


async def test_enqueue_export_enforces_revision_header(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет обязательность и актуальность If-Match при постановке экспорта."""

    plan_id, _ = await create_verified_plan(client=client, db_session=db_session, project=project)
    url = f'/api/projects/{project.id}/plans/{plan_id}/exports'

    missing_response = await client.post(url)
    stale_response = await client.post(url, headers={'If-Match': '2'})

    assert missing_response.status_code == 428
    assert stale_response.status_code == 409
    assert stale_response.json()['detail'] == 'Plan revision conflict: expected=2, actual=1'


async def test_get_export_hides_other_project(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root,
) -> None:
    """Проверяет запрет чтения комплекта через ID другого проекта."""

    plan_id, _ = await create_verified_plan(client=client, db_session=db_session, project=project)
    job = await ExportService(async_session=db_session).enqueue_export(
        project_id=project.id,
        plan_id=plan_id,
        expected_revision=1,
    )
    await JobService(async_session=db_session).claim_next_job()
    await publish_required_artifacts(
        db_session=db_session,
        project=project,
        job=job,
        file_storage_root=file_storage_root,
    )
    export = await ExportService(async_session=db_session).publish_export(
        job_id=job.id,
        export_version='dxf-export/1',
    )

    response = await client.get(f'/api/projects/{project.id + 1000}/plans/{plan_id}/exports/{export.id}')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Export with id={export.id} not found'}
