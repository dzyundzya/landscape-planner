from app.services.exceptions.base import AppError


class PlanValidationUnavailableError(AppError):
    """Для текущей ревизии плана ещё нет результата Validator."""

    def __init__(self, plan_id: int, plan_revision: int) -> None:
        super().__init__(f'Plan with id={plan_id} has no validation for revision={plan_revision}')


class InvalidPlanValidationError(AppError):
    """Результат Validator не согласован с планом и его входами."""
