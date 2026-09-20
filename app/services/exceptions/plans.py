from app.services.exceptions.base import AppError, NotFoundError


class PlanNotFoundError(NotFoundError):
    """План проекта не найден."""

    def __init__(self, plan_id: int) -> None:
        super().__init__(entity='план', obj_id=plan_id)


class CurrentPlanNotFoundError(NotFoundError):
    """Текущий план проекта не найден."""

    def __init__(self, project_id: int) -> None:
        super().__init__(entity='текущий план проекта', obj_id=project_id)


class PlanPrerequisiteError(AppError):
    """Проект ещё не готов к генерации плана."""


class InvalidPlanError(AppError):
    """Результат генератора не соответствует зафиксированным входам."""


class PlanPreviewUnavailableError(AppError):
    """Для плана отсутствует подготовленная геометрия preview."""

    def __init__(self, plan_id: int) -> None:
        super().__init__(f'Для плана с id={plan_id} отсутствует подготовленное представление')
