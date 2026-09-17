from typing import Annotated

from fastapi import Depends, Header

from app.services.exceptions.plantings import InvalidPlanRevisionError, PlanRevisionRequiredError


def get_expected_plan_revision(
    if_match: Annotated[str | None, Header(alias='If-Match')] = None,
) -> int:
    """Извлекает положительную ревизию плана из заголовка If-Match."""

    if if_match is None:
        raise PlanRevisionRequiredError('If-Match header with plan revision is required')

    value = if_match.strip()
    if value.startswith('W/'):
        value = value[2:]
    value = value.strip('"')
    try:
        revision = int(value)
    except ValueError as exc:
        raise InvalidPlanRevisionError('If-Match must contain a positive integer plan revision') from exc
    if revision < 1:
        raise InvalidPlanRevisionError('If-Match must contain a positive integer plan revision')
    return revision


ExpectedPlanRevisionDep = Annotated[int, Depends(get_expected_plan_revision)]
