from uuid import UUID

from app.services.exceptions.base import AppError, NotFoundError


class PlantingNotFoundError(NotFoundError):
    """Посадка не найдена в плане."""

    def __init__(self, planting_id: UUID) -> None:
        AppError.__init__(self, f'Planting with id={planting_id} not found')


class PlantingValidationError(AppError):
    """Посадка нарушает границу, лимит или проектный интервал."""


class PlanRevisionConflictError(AppError):
    """План был изменён после получения клиентом."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f'Plan revision conflict: expected={expected}, actual={actual}')


class PlanRevisionRequiredError(AppError):
    """Запрос изменения не содержит ожидаемую ревизию плана."""


class InvalidPlanRevisionError(AppError):
    """Заголовок ревизии плана имеет неверный формат."""
