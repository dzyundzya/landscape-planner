from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectModel
from app.schemas.plan import PlanGenerationSummarySchema
from app.services.jobs import JobService
from app.services.plans import PlanService
from tests.api.test_plans import create_current_config


async def publish_empty_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> int:
    """Публикует пустой план для проверки ручного редактирования."""

    config = await create_current_config(db_session=db_session, project_id=project.id)
    response = await client.post(f'/api/projects/{project.id}/plans')
    job = await JobService(async_session=db_session).claim_next_job()
    assert job is not None
    assert job.id == response.json()['id']

    plan = await PlanService(async_session=db_session).publish_plan(
        project_id=project.id,
        project_file_id=job.project_file_id,
        analysis_id=config.analysis_id,
        config_snapshot_id=config.id,
        job_id=job.id,
        generator_version='hex-grid/1',
        generation_summary=PlanGenerationSummarySchema(
            candidate_count=0,
            tree_count=0,
            bush_count=0,
            rejected_candidate_count=0,
        ),
        plantings=[],
    )
    return plan.id


async def test_planting_lifecycle_updates_plan_revision(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет добавление, изменение и физическое удаление ручной посадки."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    collection_url = f'/api/projects/{project.id}/plans/{plan_id}/plantings'

    create_response = await client.post(
        collection_url,
        headers={'If-Match': '"1"'},
        json={'type': 'tree', 'x_m': 1, 'y_m': 1, 'species': 'Липа'},
    )
    created = create_response.json()

    assert create_response.status_code == 201
    assert create_response.headers['etag'] == '"2"'
    assert created['plan_revision'] == 2
    assert created['planting']['source'] == 'manual'
    assert created['planting']['species'] == 'Липа'

    planting_id = created['planting']['public_id']
    update_response = await client.patch(
        f'{collection_url}/{planting_id}',
        headers={'If-Match': 'W/"2"'},
        json={'type': 'bush', 'x_m': 2, 'species': None},
    )
    updated = update_response.json()

    assert update_response.status_code == 200
    assert update_response.headers['etag'] == '"3"'
    assert updated['plan_revision'] == 3
    assert updated['planting']['type'] == 'bush'
    assert float(updated['planting']['x_m']) == 2
    assert updated['planting']['species'] is None

    delete_response = await client.delete(
        f'{collection_url}/{planting_id}',
        headers={'If-Match': '3'},
    )

    assert delete_response.status_code == 204
    assert delete_response.headers['etag'] == '"4"'

    plan_response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}')
    assert plan_response.json()['revision'] == 4
    assert plan_response.json()['plantings'] == []


async def test_add_planting_requires_current_revision(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет обязательность If-Match и отклонение устаревшей ревизии."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    url = f'/api/projects/{project.id}/plans/{plan_id}/plantings'
    payload = {'type': 'tree', 'x_m': 1, 'y_m': 1}

    missing_response = await client.post(url, json=payload)
    invalid_response = await client.post(url, headers={'If-Match': 'latest'}, json=payload)
    created_response = await client.post(url, headers={'If-Match': '1'}, json=payload)
    stale_response = await client.post(
        url,
        headers={'If-Match': '1'},
        json={'type': 'bush', 'x_m': 4, 'y_m': 1},
    )

    assert missing_response.status_code == 428
    assert invalid_response.status_code == 400
    assert created_response.status_code == 201
    assert stale_response.status_code == 409
    assert stale_response.json()['detail'] == 'Plan revision conflict: expected=1, actual=2'

    plan_response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}')
    assert plan_response.json()['revision'] == 2
    assert len(plan_response.json()['plantings']) == 1


async def test_add_planting_rejects_invalid_geometry_without_mutation(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет отклонение посадок вне границы и ближе заданного интервала."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    url = f'/api/projects/{project.id}/plans/{plan_id}/plantings'

    outside_response = await client.post(
        url,
        headers={'If-Match': '1'},
        json={'type': 'tree', 'x_m': 20, 'y_m': 20},
    )
    first_response = await client.post(
        url,
        headers={'If-Match': '1'},
        json={'type': 'tree', 'x_m': 1, 'y_m': 1},
    )
    too_close_response = await client.post(
        url,
        headers={'If-Match': '2'},
        json={'type': 'tree', 'x_m': 2, 'y_m': 1},
    )

    assert outside_response.status_code == 422
    assert 'outside the project boundary' in outside_response.json()['detail']
    assert first_response.status_code == 201
    assert too_close_response.status_code == 422
    assert 'require distance 5.0 m' in too_close_response.json()['detail']

    plan_response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}')
    assert plan_response.json()['revision'] == 2
    assert len(plan_response.json()['plantings']) == 1
