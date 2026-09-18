from copy import deepcopy

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisModel,
    JobModel,
    JobStatus,
    JobType,
    ProjectFileFormat,
    ProjectFileModel,
    ProjectFileStatus,
    ProjectModel,
)


async def create_analysis(db_session: AsyncSession, project_id: int) -> AnalysisModel:
    """Создаёт текущий анализ с известным слоем для тестов конфигурации."""

    project_file = ProjectFileModel(
        project_id=project_id,
        version=1,
        format=ProjectFileFormat.DXF,
        status=ProjectFileStatus.READY,
        original_name='site.dxf',
        storage_key=f'projects/{project_id}/sources/config-test.dxf',
        content_type='application/dxf',
        size_bytes=100,
        sha256='a' * 64,
    )
    db_session.add(project_file)
    await db_session.flush()

    job = JobModel(
        project_id=project_id,
        project_file_id=project_file.id,
        type=JobType.ANALYZE,
        status=JobStatus.SUCCEEDED,
        input_data={},
        result={},
    )
    db_session.add(job)
    await db_session.flush()

    analysis = AnalysisModel(
        project_id=project_id,
        project_file_id=project_file.id,
        job_id=job.id,
        schema_version=1,
        result={
            'layers': [
                {
                    'name': 'SITE',
                    'entity_count': 1,
                    'entity_counts': {'LWPOLYLINE': 1},
                }
            ]
        },
    )
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)
    return analysis


def config_payload() -> dict[str, object]:
    """Возвращает валидные подтверждённые настройки проекта."""

    return {
        'coordinate_unit': 'millimeter',
        'territory_type': 'courtyard',
        'boundary': {
            'type': 'Polygon',
            'coordinate_space': 'local_meters',
            'coordinates': [[[0, 0], [20, 0], [20, 10], [0, 0]]],
        },
        'layer_mappings': [
            {
                'layer': 'SITE',
                'object_type': 'other_obstacle',
                'attributes': {'confirmed_by': 'user'},
            }
        ],
        'generation': {
            'max_trees': 20,
            'max_bushes': 40,
            'tree_tree_distance_m': 5,
            'bush_bush_distance_m': 1.5,
            'tree_bush_distance_m': 2,
            'grid_spacing_m': 1,
        },
    }


async def test_save_config_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет сохранение подтверждённых настроек текущего анализа."""

    analysis = await create_analysis(db_session=db_session, project_id=project.id)

    response = await client.put(f'/api/projects/{project.id}/config', json=config_payload())
    data = response.json()

    assert response.status_code == 200
    assert data['project_id'] == project.id
    assert data['analysis_id'] == analysis.id
    assert data['version'] == 1
    assert data['schema_version'] == 2
    assert data['coordinate_unit'] == 'millimeter'
    assert float(data['unit_scale_to_meters']) == 0.001
    assert data['rules_status'] == 'needs_verification'
    assert data['rules_version'] == 'draft-empty'
    assert len(data['rules_sha256']) == 64
    assert data['territory_type'] == 'courtyard'
    assert data['plant_catalog_status'] == 'needs_verification'
    assert data['plant_catalog_version'] == 'moscow-assortment-3709b4ca24b2'
    assert len(data['plant_catalog_sha256']) == 64
    assert len(data['content_sha256']) == 64
    assert data['boundary']['coordinate_space'] == 'local_meters'


async def test_save_config_is_idempotent_and_versions_changes(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет повторный PUT и создание версии только при изменении настроек."""

    await create_analysis(db_session=db_session, project_id=project.id)
    payload = config_payload()

    first_response = await client.put(f'/api/projects/{project.id}/config', json=payload)
    repeated_response = await client.put(f'/api/projects/{project.id}/config', json=payload)
    changed_payload = deepcopy(payload)
    changed_payload['generation']['max_trees'] = 25  # type: ignore[index]
    changed_response = await client.put(f'/api/projects/{project.id}/config', json=changed_payload)

    assert repeated_response.json()['id'] == first_response.json()['id']
    assert repeated_response.json()['version'] == 1
    assert changed_response.json()['id'] != first_response.json()['id']
    assert changed_response.json()['version'] == 2
    assert changed_response.json()['content_sha256'] != first_response.json()['content_sha256']


async def test_save_config_requires_current_analysis(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет запрет настройки проекта до анализа текущего исходника."""

    response = await client.put(f'/api/projects/{project.id}/config', json=config_payload())

    assert response.status_code == 409
    assert response.json() == {'detail': f'Project with id={project.id} has no source file'}


async def test_save_config_rejects_unknown_layer(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет mapping слоя, отсутствующего в текущем анализе."""

    await create_analysis(db_session=db_session, project_id=project.id)
    payload = config_payload()
    payload['layer_mappings'][0]['layer'] = 'UNKNOWN'  # type: ignore[index]

    response = await client.put(f'/api/projects/{project.id}/config', json=payload)

    assert response.status_code == 422
    assert response.json() == {'detail': 'Layer mappings reference unknown layers: UNKNOWN'}


async def test_save_config_rejects_open_boundary(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет отклонение незамкнутой границы участка."""

    await create_analysis(db_session=db_session, project_id=project.id)
    payload = config_payload()
    payload['boundary']['coordinates'][0][-1] = [0, 5]  # type: ignore[index]

    response = await client.put(f'/api/projects/{project.id}/config', json=payload)

    assert response.status_code == 422
