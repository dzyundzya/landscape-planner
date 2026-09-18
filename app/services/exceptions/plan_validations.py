from app.services.exceptions.base import AppError


class PlanValidationUnavailableError(AppError):
    """Для текущей ревизии плана ещё нет результата Validator."""

    def __init__(self, plan_id: int, plan_revision: int) -> None:
        super().__init__(f'У плана с id={plan_id} отсутствует проверка ревизии {plan_revision}')


class InvalidPlanValidationError(AppError):
    """Результат Validator не согласован с планом и его входами."""


class PlanValidationAlreadyExistsError(AppError):
    """Текущая ревизия плана уже имеет результат Validator."""

    def __init__(self, plan_id: int, plan_revision: int) -> None:
        super().__init__(f'План с id={plan_id} ревизии {plan_revision} уже проверен')
