from sqlalchemy import select

from app.models import FileArtifactKind, FileArtifactModel
from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class FileArtifactCRUDRepository(BaseCRUDRepository[FileArtifactModel]):
    """Операции с файлами результатов проекта."""

    model = FileArtifactModel

    async def get_artifact_by_job_and_kind(
        self,
        job_id: int,
        kind: FileArtifactKind,
    ) -> FileArtifactModel | None:
        """Возвращает результат заданного вида для фоновой задачи."""

        return await self.session.scalar(
            select(FileArtifactModel).where(
                FileArtifactModel.job_id == job_id,
                FileArtifactModel.kind == kind,
            )
        )

    async def get_artifact_for_project(self, artifact_id: int, project_id: int) -> FileArtifactModel | None:
        """Возвращает файл результата только в пределах указанного проекта."""

        return await self.session.scalar(
            select(FileArtifactModel).where(
                FileArtifactModel.id == artifact_id,
                FileArtifactModel.project_id == project_id,
            )
        )
