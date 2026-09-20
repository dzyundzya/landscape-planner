from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.api.test_plans import publish_plan
from tests.api.test_plantings import publish_empty_plan

from app.models import PlanStatus, ProjectModel, ValidationStatus
from app.schemas.plan_validation import (
    CheckResultSchema,
    PlanValidationPublishSchema,
    ValidationSummarySchema,
)
from app.services.exceptions.plan_validations import InvalidPlanValidationError
from app.services.exceptions.plantings import PlanRevisionConflictError
from app.services.plan_validations import PlanValidationService


def passed_boundary_check() -> CheckResultSchema:
    """Создаёт успешную геометрическую проверку без выдуманной нормы."""

    return CheckResultSchema(
        check_type='project_boundary',
        status=ValidationStatus.PASSED,
        reason='All plantings are strictly inside the confirmed boundary',
    )


async def test_publish_validation_adds_unverified_rules_check(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет сохранение фактов и блокировку verified при непроверенных нормах."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    service = PlanValidationService(async_session=db_session)
    data = PlanValidationPublishSchema(
        validator_version='validator/1',
        checks=[passed_boundary_check()],
    )

    validation = await service.publish_validation(
        project_id=project.id,
        plan_id=plan_id,
        plan_revision=1,
        data=data,
    )
    repeated = await service.publish_validation(
        project_id=project.id,
        plan_id=plan_id,
        plan_revision=1,
        data=PlanValidationPublishSchema(
            validator_version='ignored/2',
            checks=[passed_boundary_check()],
        ),
    )
    plan = await service.plan_repository.get_plan_for_project(plan_id=plan_id, project_id=project.id)

    assert repeated.id == validation.id
    assert validation.status is ValidationStatus.NEEDS_VERIFICATION
    assert validation.validator_version == 'validator/1'
    assert validation.summary == {'total': 2, 'passed': 1, 'failed': 0, 'needs_verification': 1}
    assert validation.checks[1]['check_type'] == 'normative_rules_status'
    assert validation.rules_status == 'needs_verification'
    assert plan is not None
    assert plan.status is PlanStatus.NEEDS_VERIFICATION


async def test_publish_validation_marks_failed_plan_invalid(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет перевод плана в invalid при хотя бы одной проваленной проверке."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    service = PlanValidationService(async_session=db_session)

    validation = await service.publish_validation(
        project_id=project.id,
        plan_id=plan_id,
        plan_revision=1,
        data=PlanValidationPublishSchema(
            validator_version='validator/1',
            checks=[
                CheckResultSchema(
                    check_type='source_clearance',
                    status=ValidationStatus.FAILED,
                    actual='1.5',
                    required='2.0',
                    unit='m',
                    rule_id='TEST_ONLY_RULE',
                    rule_version='1',
                    source_object_id='entity:42',
                    reason='Required clearance is not met',
                )
            ],
        ),
    )
    plan = await service.plan_repository.get_plan_for_project(plan_id=plan_id, project_id=project.id)

    assert validation.status is ValidationStatus.FAILED
    assert validation.summary['failed'] == 1
    assert plan is not None
    assert plan.status is PlanStatus.INVALID


async def test_publish_validation_rejects_stale_revision(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет публикации результата для неактуальной ревизии плана."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)

    with pytest.raises(PlanRevisionConflictError, match='ожидалась 2, фактическая 1'):
        await PlanValidationService(async_session=db_session).publish_validation(
            project_id=project.id,
            plan_id=plan_id,
            plan_revision=2,
            data=PlanValidationPublishSchema(
                validator_version='validator/1',
                checks=[passed_boundary_check()],
            ),
        )


async def test_publish_validation_rejects_unknown_planting(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет факта со ссылкой на чужую или отсутствующую посадку."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)

    with pytest.raises(InvalidPlanValidationError, match='неизвестную посадку'):
        await PlanValidationService(async_session=db_session).publish_validation(
            project_id=project.id,
            plan_id=plan_id,
            plan_revision=1,
            data=PlanValidationPublishSchema(
                validator_version='validator/1',
                checks=[
                    CheckResultSchema(
                        check_type='project_boundary',
                        status=ValidationStatus.PASSED,
                        planting_id=uuid4(),
                        reason='Planting is inside the boundary',
                    )
                ],
            ),
        )


async def test_publish_validation_requires_check_for_every_planting(
    client,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет невозможность опубликовать неполную проверку посадок плана."""

    plan_id, _ = await publish_plan(client=client, db_session=db_session, project=project)

    with pytest.raises(InvalidPlanValidationError, match='отсутствуют результаты для посадки'):
        await PlanValidationService(async_session=db_session).publish_validation(
            project_id=project.id,
            plan_id=plan_id,
            plan_revision=1,
            data=PlanValidationPublishSchema(
                validator_version='validator/1',
                checks=[passed_boundary_check()],
            ),
        )


def test_check_result_requires_complete_measurement() -> None:
    """Проверяет обязательность actual, required и unit как единого измерения."""

    with pytest.raises(ValidationError, match='должны быть указаны вместе'):
        CheckResultSchema(
            check_type='source_clearance',
            status=ValidationStatus.FAILED,
            actual='1.5',
            reason='Incomplete measurement',
        )


def test_validation_summary_rejects_inconsistent_total() -> None:
    """Проверяет согласованность суммы статусов с общим числом проверок."""

    with pytest.raises(ValidationError, match='должны соответствовать общему количеству'):
        ValidationSummarySchema(total=2, passed=1, failed=0, needs_verification=0)
