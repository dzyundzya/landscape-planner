from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.api.test_plans import create_current_config
from tests.api.test_plantings import publish_empty_plan

from app.models import (
    FileArtifactKind,
    JobStatus,
    NormativeRulesStatus,
    PlantCatalogStatus,
    ProjectModel,
    ValidationStatus,
)
from app.schemas.plan import PlanGenerationSummarySchema
from app.schemas.plan_validation import CheckResultSchema, PlanValidationPublishSchema
from app.services.exceptions.exports import ExportPrerequisiteError, InvalidExportError
from app.services.exports import REQUIRED_EXPORT_KINDS, ExportService
from app.services.file_artifacts import FileArtifactService
from app.services.jobs import JobService
from app.services.plan_validations import PlanValidationService
from app.services.plans import PlanService
from app.storage import LocalFileStorage


async def create_verified_plan(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> tuple[int, int]:
    """Создаёт пустой план с синтетически подтверждённым тестовым набором правил."""

    config = await create_current_config(db_session=db_session, project_id=project.id)
    config.rules_status = NormativeRulesStatus.VERIFIED
    config.rules_version = 'TEST_ONLY/1'
    config.rules_sha256 = 'c' * 64
    config.plant_catalog_status = PlantCatalogStatus.VERIFIED
    await db_session.commit()

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
    validation = await PlanValidationService(async_session=db_session).publish_validation(
        project_id=project.id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        data=PlanValidationPublishSchema(
            validator_version='validator/1',
            checks=[
                CheckResultSchema(
                    check_type='project_boundary',
                    status=ValidationStatus.PASSED,
                    reason='The empty plan is inside the confirmed boundary',
                )
            ],
        ),
    )
    return plan.id, validation.id


async def enqueue_verified_export(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
):
    """Создаёт проверенный план и ставит его экспорт в очередь."""

    plan_id, validation_id = await create_verified_plan(client=client, db_session=db_session, project=project)
    job = await ExportService(async_session=db_session).enqueue_export(
        project_id=project.id,
        plan_id=plan_id,
        expected_revision=1,
    )
    return plan_id, validation_id, job


async def publish_required_artifacts(
    db_session: AsyncSession,
    project: ProjectModel,
    job,
    file_storage_root: Path,
) -> None:
    """Публикует четыре обязательных файла выполняющейся задачи экспорта."""

    service = FileArtifactService(
        async_session=db_session,
        storage=LocalFileStorage(root=file_storage_root, max_size_bytes=1024 * 1024),
    )
    for kind in REQUIRED_EXPORT_KINDS:
        await service.create_artifact(
            project_id=project.id,
            project_file_id=job.project_file_id,
            job_id=job.id,
            kind=kind,
            source=BytesIO(f'content:{kind.value}'.encode()),
        )


async def test_enqueue_export_captures_immutable_plan_snapshot(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет идемпотентную очередь и сохранность снимка после правки плана."""

    plan_id, validation_id, job = await enqueue_verified_export(
        client=client,
        db_session=db_session,
        project=project,
    )
    repeated = await ExportService(async_session=db_session).enqueue_export(
        project_id=project.id,
        plan_id=plan_id,
        expected_revision=1,
    )

    edit_response = await client.post(
        f'/api/projects/{project.id}/plans/{plan_id}/plantings',
        headers={'If-Match': '1'},
        json={'type': 'tree', 'x_m': 1, 'y_m': 1},
    )

    assert repeated.id == job.id
    assert job.input_data['plan_revision'] == 1
    assert job.input_data['validation']['id'] == validation_id
    assert job.input_data['plan']['plantings'] == []
    assert edit_response.status_code == 201
    assert edit_response.json()['plan_revision'] == 2
    assert job.input_data['plan_revision'] == 1
    assert job.input_data['plan']['plantings'] == []


async def test_enqueue_export_requires_passed_validation(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет экспорта без Validator и с непроверенными нормами."""

    plan_without_validation = await publish_empty_plan(client=client, db_session=db_session, project=project)
    service = ExportService(async_session=db_session)
    with pytest.raises(ExportPrerequisiteError, match='отсутствует проверка'):
        await service.enqueue_export(
            project_id=project.id,
            plan_id=plan_without_validation,
            expected_revision=1,
        )

    validation = await PlanValidationService(async_session=db_session).publish_validation(
        project_id=project.id,
        plan_id=plan_without_validation,
        plan_revision=1,
        data=PlanValidationPublishSchema(
            validator_version='validator/1',
            checks=[
                CheckResultSchema(
                    check_type='project_boundary',
                    status=ValidationStatus.PASSED,
                    reason='Boundary check passed',
                )
            ],
        ),
    )
    assert validation.status is ValidationStatus.NEEDS_VERIFICATION

    with pytest.raises(ExportPrerequisiteError, match='не проверен для экспорта'):
        await service.enqueue_export(
            project_id=project.id,
            plan_id=plan_without_validation,
            expected_revision=1,
        )


async def test_publish_export_completes_job_with_manifest(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет атомарную публикацию полного комплекта и завершение задачи."""

    plan_id, validation_id, queued_job = await enqueue_verified_export(
        client=client,
        db_session=db_session,
        project=project,
    )
    job = await JobService(async_session=db_session).claim_next_job()
    assert job is not None
    assert job.id == queued_job.id
    await publish_required_artifacts(
        db_session=db_session,
        project=project,
        job=job,
        file_storage_root=file_storage_root,
    )

    service = ExportService(async_session=db_session)
    export = await service.publish_export(job_id=job.id, export_version='dxf-export/1')
    repeated = await service.publish_export(job_id=job.id, export_version='ignored/2')
    completed_job = await service.enqueue_export(
        project_id=project.id,
        plan_id=plan_id,
        expected_revision=1,
    )
    saved = await service.get_export(project_id=project.id, plan_id=plan_id, export_id=export.id)

    assert repeated.id == export.id
    assert completed_job.id == job.id
    assert completed_job.status is JobStatus.SUCCEEDED
    assert export.plan_revision == 1
    assert export.validation_id == validation_id
    assert [item['kind'] for item in export.manifest] == [kind.value for kind in REQUIRED_EXPORT_KINDS]
    assert len(saved.artifacts) == 4
    assert {artifact.export_id for artifact in saved.artifacts} == {export.id}
    assert job.status is JobStatus.SUCCEEDED
    assert job.result is not None
    assert job.result['export_id'] == export.id
    assert job.result['plan_revision'] == 1


async def test_publish_export_rejects_incomplete_artifacts(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет запрет публикации неполного комплекта файлов."""

    _, _, queued_job = await enqueue_verified_export(client=client, db_session=db_session, project=project)
    job = await JobService(async_session=db_session).claim_next_job()
    assert job is not None
    assert job.id == queued_job.id
    await FileArtifactService(
        async_session=db_session,
        storage=LocalFileStorage(root=file_storage_root, max_size_bytes=1024 * 1024),
    ).create_artifact(
        project_id=project.id,
        project_file_id=job.project_file_id,
        job_id=job.id,
        kind=FileArtifactKind.RESULT_DXF,
        source=BytesIO(b'incomplete dxf'),
    )

    with pytest.raises(InvalidExportError, match='должна опубликовать'):
        await ExportService(async_session=db_session).publish_export(
            job_id=job.id,
            export_version='dxf-export/1',
        )

    assert job.status is JobStatus.RUNNING
