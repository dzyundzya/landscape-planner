from sqlalchemy import select

from app.models import PlanValidationModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class PlanValidationCRUDRepository(BaseCRUDRepository[PlanValidationModel]):
    """Операции с неизменяемыми результатами Validator."""

    model = PlanValidationModel

    async def get_for_plan_revision(self, plan_id: int, plan_revision: int) -> PlanValidationModel | None:
        """Возвращает результат проверки конкретной ревизии плана."""

        return await self.session.scalar(
            select(PlanValidationModel).where(
                PlanValidationModel.plan_id == plan_id,
                PlanValidationModel.plan_revision == plan_revision,
            )
        )
