from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisModel,
    ConfigSnapshotModel,
    CoordinateUnit,
    JobModel,
    JobStatus,
    JobType,
    NormativeRulesStatus,
    PlanStatus,
    ProjectFileFormat,
    ProjectFileModel,
    ProjectFileStatus,
    ProjectModel,
)
from app.schemas.plan import PlanGenerationSummarySchema
from app.services.jobs import JobService
from app.services.plans import PlanService


async def create_current_config(db_session: AsyncSession, project_id: int) -> ConfigSnapshotModel:
    """Создаёт полную цепочку входов для тестовой генерации плана."""

    project_file = ProjectFileModel(
        project_id=project_id,
        version=1,
        format=ProjectFileFormat.DXF,
        status=ProjectFileStatus.READY,
        original_name='site.dxf',
        storage_key=f'projects/{project_id}/sources/plan-test.dxf',
        content_type='application/dxf',
        size_bytes=100,
        sha256='a' * 64,
    )
    db_session.add(project_file)
    await db_session.flush()

    analysis_job = JobModel(
        project_id=project_id,
        project_file_id=project_file.id,
        type=JobType.ANALYZE,
        status=JobStatus.SUCCEEDED,
        input_data={},
        result={},
    )
    db_session.add(analysis_job)
    await db_session.flush()

    analysis = AnalysisModel(
        project_id=project_id,
        project_file_id=project_file.id,
        job_id=analysis_job.id,
        schema_version=1,
        result={'layers': []},
    )
    db_session.add(analysis)
    await db_session.flush()

    config = ConfigSnapshotModel(
        project_id=project_id,
        analysis_id=analysis.id,
        version=1,
        schema_version=1,
        coordinate_unit=CoordinateUnit.METER,
        unit_scale_to_meters=Decimal('1'),
        boundary={
            'type': 'Polygon',
            'coordinate_space': 'local_meters',
            'coordinates': [[[0, 0], [10, 0], [0, 10], [0, 0]]],
        },
        layer_mappings=[],
        generation={
            'max_trees': 20,
            'max_bushes': 40,
            'tree_tree_distance_m': 5,
            'bush_bush_distance_m': 1.5,
            'tree_bush_distance_m': 2,
            'grid_spacing_m': 1,
        },
        rules_status=NormativeRulesStatus.NEEDS_VERIFICATION,
        rules_version=None,
        rules_sha256=None,
        content_sha256='b' * 64,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


def generation_summary() -> PlanGenerationSummarySchema:
    """Возвращает согласованную сводку генератора."""

    return PlanGenerationSummarySchema(
        candidate_count=10,
        tree_count=2,
        bush_count=3,
        rejected_candidate_count=5,
        warnings=['Normative rules require verification'],
    )


async def publish_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> tuple[int, int]:
    """Создаёт входы, запускает и публикует тестовый план."""

    config = await create_current_config(db_session=db_session, project_id=project.id)
    response = await client.post(f'/api/projects/{project.id}/plans')
    job_id = response.json()['id']
    job = await JobService(async_session=db_session).claim_next_job()
    assert job is not None
    assert job.id == job_id

    plan = await PlanService(async_session=db_session).publish_plan(
        project_id=project.id,
        project_file_id=job.project_file_id,
        analysis_id=config.analysis_id,
        config_snapshot_id=config.id,
        job_id=job.id,
        generator_version='hex-grid/1',
        generation_summary=generation_summary(),
    )
    return plan.id, job.id


async def test_enqueue_plan_generation(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет постановку генерации в очередь без дубликатов для конфигурации."""

    config = await create_current_config(db_session=db_session, project_id=project.id)

    first_response = await client.post(f'/api/projects/{project.id}/plans')
    second_response = await client.post(f'/api/projects/{project.id}/plans')
    job_data = first_response.json()

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert second_response.json()['id'] == job_data['id']
    assert job_data['type'] == 'generate_plan'
    assert job_data['status'] == 'queued'
    assert job_data['project_file_id'] is not None

    job = await db_session.scalar(select(JobModel).where(JobModel.id == job_data['id']))
    assert job is not None
    assert job.input_data['config_snapshot_id'] == config.id
    assert job.input_data['config_content_sha256'] == config.content_sha256
    assert job.input_data['rules_status'] == 'needs_verification'


async def test_enqueue_plan_requires_project_inputs(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет запрет генерации проекта без исходника и конфигурации."""

    response = await client.post(f'/api/projects/{project.id}/plans')

    assert response.status_code == 409
    assert response.json() == {'detail': f'Project with id={project.id} has no source file'}


async def test_get_published_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет публикацию и чтение плана с зафиксированными входами."""

    plan_id, job_id = await publish_plan(client=client, db_session=db_session, project=project)

    response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}')
    data = response.json()

    assert response.status_code == 200
    assert data['id'] == plan_id
    assert data['job_id'] == job_id
    assert data['revision'] == 1
    assert data['status'] == PlanStatus.NEEDS_VERIFICATION
    assert data['generator_version'] == 'hex-grid/1'
    assert data['generation_summary'] == generation_summary().model_dump(mode='json')


async def test_get_plan_hides_other_project(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет чтения плана через ID другого проекта."""

    plan_id, _ = await publish_plan(client=client, db_session=db_session, project=project)

    response = await client.get(f'/api/projects/{project.id + 1000}/plans/{plan_id}')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Plan with id={plan_id} not found'}
