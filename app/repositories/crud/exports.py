from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ExportModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class ExportCRUDRepository(BaseCRUDRepository[ExportModel]):
    """Операции с готовыми комплектами экспорта."""

    model = ExportModel

    async def get_by_job_id(self, job_id: int) -> ExportModel | None:
        """Возвращает экспорт, опубликованный указанной задачей."""

        return await self.session.scalar(
            select(ExportModel).options(selectinload(ExportModel.artifacts)).where(ExportModel.job_id == job_id)
        )

    async def get_latest_for_plan_revision(self, plan_id: int, plan_revision: int) -> ExportModel | None:
        """Возвращает последний успешный экспорт ревизии плана."""

        return await self.session.scalar(
            select(ExportModel)
            .where(
                ExportModel.plan_id == plan_id,
                ExportModel.plan_revision == plan_revision,
            )
            .order_by(ExportModel.created_at.desc(), ExportModel.id.desc())
            .limit(1)
        )

    async def get_for_project_plan(self, export_id: int, project_id: int, plan_id: int) -> ExportModel | None:
        """Возвращает экспорт только внутри заданных проекта и плана."""

        return await self.session.scalar(
            select(ExportModel)
            .options(selectinload(ExportModel.artifacts))
            .where(
                ExportModel.id == export_id,
                ExportModel.project_id == project_id,
                ExportModel.plan_id == plan_id,
            )
        )
