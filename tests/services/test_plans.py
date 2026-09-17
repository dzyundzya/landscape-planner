import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.api.test_plans import create_current_config

from app.models import JobStatus, ProjectModel
from app.schemas.plan import PlanGenerationSummarySchema
from app.services.exceptions.plans import InvalidPlanError
from app.services.jobs import JobService
from app.services.plans import PlanService


async def test_publish_plan_completes_job_atomically(
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет создание плана вместе с успешным завершением задачи."""

    config = await create_current_config(db_session=db_session, project_id=project.id)
    service = PlanService(async_session=db_session)
    job = await service.enqueue_plan_generation(project_id=project.id)
    claimed_job = await JobService(async_session=db_session).claim_next_job()
    assert claimed_job is not None
    assert claimed_job.id == job.id

    summary = PlanGenerationSummarySchema(
        candidate_count=3,
        tree_count=1,
        bush_count=1,
        rejected_candidate_count=1,
    )
    plan = await service.publish_plan(
        project_id=project.id,
        project_file_id=job.project_file_id,
        analysis_id=config.analysis_id,
        config_snapshot_id=config.id,
        job_id=job.id,
        generator_version='planner/1',
        generation_summary=summary,
    )

    assert plan.revision == 1
    assert job.status is JobStatus.SUCCEEDED
    assert job.result == {'plan_id': plan.id, 'revision': 1}
    assert job.finished_at is not None

    repeated_plan = await service.publish_plan(
        project_id=project.id,
        project_file_id=job.project_file_id,
        analysis_id=config.analysis_id,
        config_snapshot_id=config.id,
        job_id=job.id,
        generator_version='ignored-after-publication',
        generation_summary=summary,
    )
    assert repeated_plan.id == plan.id


async def test_publish_plan_rejects_count_above_config_limit(
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет результата, превышающего лимит конфигурации."""

    config = await create_current_config(db_session=db_session, project_id=project.id)
    service = PlanService(async_session=db_session)
    job = await service.enqueue_plan_generation(project_id=project.id)
    await JobService(async_session=db_session).claim_next_job()

    with pytest.raises(InvalidPlanError, match='tree count'):
        await service.publish_plan(
            project_id=project.id,
            project_file_id=job.project_file_id,
            analysis_id=config.analysis_id,
            config_snapshot_id=config.id,
            job_id=job.id,
            generator_version='planner/1',
            generation_summary=PlanGenerationSummarySchema(
                candidate_count=21,
                tree_count=21,
                bush_count=0,
                rejected_candidate_count=0,
            ),
        )


def test_generation_summary_rejects_inconsistent_counts() -> None:
    """Проверяет согласованность числа кандидатов, посадок и отклонений."""

    with pytest.raises(ValidationError):
        PlanGenerationSummarySchema(
            candidate_count=2,
            tree_count=1,
            bush_count=1,
            rejected_candidate_count=1,
        )
