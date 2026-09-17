from sqlalchemy import select

from app.models import AnalysisModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class AnalysisCRUDRepository(BaseCRUDRepository[AnalysisModel]):
    """Операции с результатами анализа DXF."""

    model = AnalysisModel

    async def get_latest_for_project_file(self, project_file_id: int) -> AnalysisModel | None:
        """Возвращает последний анализ заданной версии исходника."""

        return await self.session.scalar(
            select(AnalysisModel)
            .where(AnalysisModel.project_file_id == project_file_id)
            .order_by(AnalysisModel.created_at.desc(), AnalysisModel.id.desc())
            .limit(1)
        )

    async def get_by_job_id(self, job_id: int) -> AnalysisModel | None:
        """Возвращает результат, опубликованный заданием."""

        return await self.session.scalar(select(AnalysisModel).where(AnalysisModel.job_id == job_id))
