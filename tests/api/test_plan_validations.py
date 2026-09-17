from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectModel, ValidationStatus
from app.schemas.plan_validation import (
    PlanValidationPublishSchema,
)
from app.services.plan_validations import PlanValidationService
from tests.api.test_plantings import publish_empty_plan
from tests.services.test_plan_validations import passed_boundary_check


async def test_get_current_plan_report(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет чтение объяснимых фактов Validator для текущей ревизии."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    await PlanValidationService(async_session=db_session).publish_validation(
        project_id=project.id,
        plan_id=plan_id,
        plan_revision=1,
        data=PlanValidationPublishSchema(
            validator_version='validator/1',
            checks=[passed_boundary_check()],
        ),
    )

    response = await client.get(f'/api/projects/{project.id}/plans/{plan_id}/report')
    data = response.json()

    assert response.status_code == 200
    assert data['plan_id'] == plan_id
    assert data['plan_revision'] == 1
    assert data['status'] == 'needs_verification'
    assert data['summary'] == {'total': 2, 'passed': 1, 'failed': 0, 'needs_verification': 1}
    assert data['checks'][0]['status'] == ValidationStatus.PASSED
    assert data['checks'][1]['check_type'] == 'normative_rules_status'


async def test_get_plan_report_requires_current_validation(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет отсутствие отчёта до Validator и после изменения ревизии."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)
    report_url = f'/api/projects/{project.id}/plans/{plan_id}/report'

    missing_response = await client.get(report_url)
    await PlanValidationService(async_session=db_session).publish_validation(
        project_id=project.id,
        plan_id=plan_id,
        plan_revision=1,
        data=PlanValidationPublishSchema(
            validator_version='validator/1',
            checks=[passed_boundary_check()],
        ),
    )
    edit_response = await client.post(
        f'/api/projects/{project.id}/plans/{plan_id}/plantings',
        headers={'If-Match': '1'},
        json={'type': 'tree', 'x_m': 1, 'y_m': 1},
    )
    stale_response = await client.get(report_url)

    assert missing_response.status_code == 409
    assert edit_response.status_code == 201
    assert stale_response.status_code == 409
    assert stale_response.json() == {
        'detail': f'Plan with id={plan_id} has no validation for revision=2',
    }


async def test_get_plan_report_hides_other_project(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет запрет чтения отчёта через идентификатор другого проекта."""

    plan_id = await publish_empty_plan(client=client, db_session=db_session, project=project)

    response = await client.get(f'/api/projects/{project.id + 1000}/plans/{plan_id}/report')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Plan with id={plan_id} not found'}
