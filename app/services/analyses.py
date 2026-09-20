from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisModel, JobModel, JobStatus, JobType, ProjectFileFormat, ProjectFileStatus
from app.repositories.crud.analyses import AnalysisCRUDRepository
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.schemas.analysis import AnalysisResultSchema
from app.services.base import BaseService
from app.services.exceptions.analyses import AnalysisNotFoundError, AnalysisSourceNotReadyError, InvalidAnalysisError
from app.services.exceptions.jobs import JobNotFoundError, JobStateConflictError
from app.services.exceptions.projects import ProjectNotFoundError
from app.services.jobs import JobService

ANALYSIS_SCHEMA_VERSION = 2


class AnalysisService(BaseService[AnalysisCRUDRepository]):
    """Бизнес-логика анализа исходных DXF."""

    repository_class = AnalysisCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.job_repository = JobCRUDRepository(async_session=async_session)

    async def enqueue_analysis(self, project_id: int) -> JobModel:
        """Ставит анализ последней версии исходного DXF в очередь."""

        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        project_file = await self.project_file_repository.get_latest_for_project(project_id=project_id)
        if project_file is None:
            raise AnalysisSourceNotReadyError(f'У проекта с id={project_id} отсутствует исходный файл')
        self._ensure_source_ready(project_file.format, project_file.status)

        active_job = await self.job_repository.get_active_analysis(project_file_id=project_file.id)
        if active_job is not None:
            return active_job

        return await JobService(async_session=self.session).enqueue_job(
            project_id=project_id,
            project_file_id=project_file.id,
            job_type=JobType.ANALYZE,
            input_data={
                'project_file_id': project_file.id,
                'project_file_version': project_file.version,
                'project_file_sha256': project_file.sha256,
                'analysis_schema_version': ANALYSIS_SCHEMA_VERSION,
            },
        )

    async def get_current_analysis(self, project_id: int) -> AnalysisModel:
        """Возвращает последний анализ текущей версии исходника проекта."""

        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        project_file = await self.project_file_repository.get_latest_for_project(project_id=project_id)
        if project_file is None:
            raise AnalysisNotFoundError(project_id=project_id)

        analysis = await self.repository.get_latest_for_project_file(project_file_id=project_file.id)
        if analysis is None:
            raise AnalysisNotFoundError(project_id=project_id)
        return analysis

    async def publish_analysis(
        self,
        project_id: int,
        project_file_id: int,
        job_id: int,
        result: AnalysisResultSchema,
    ) -> AnalysisModel:
        """Атомарно публикует результат и завершает задачу анализа."""

        existing_analysis = await self.repository.get_by_job_id(job_id=job_id)
        if existing_analysis is not None:
            return existing_analysis

        job = await self.job_repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        self._ensure_job_matches(job=job, project_id=project_id, project_file_id=project_file_id)

        project_file = await self.project_file_repository.get_obj_by_id(obj_id=project_file_id)
        if project_file is None or project_file.project_id != project_id:
            raise InvalidAnalysisError(f'Исходный файл с id={project_file_id} не принадлежит проекту с id={project_id}')
        self._ensure_source_ready(project_file.format, project_file.status)

        analysis = await self.repository.create_obj(
            new_obj=AnalysisModel(
                project_id=project_id,
                project_file_id=project_file_id,
                job_id=job_id,
                schema_version=ANALYSIS_SCHEMA_VERSION,
                result=result.model_dump(mode='json'),
            )
        )
        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = {'analysis_id': analysis.id}
        job.error = None
        job.finished_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            'Анализ опубликован: analysis_id={}, project_id={}, project_file_id={}, job_id={}',
            analysis.id,
            project_id,
            project_file_id,
            job_id,
        )
        return analysis

    @staticmethod
    def _ensure_source_ready(file_format: ProjectFileFormat, status: ProjectFileStatus) -> None:
        if file_format is not ProjectFileFormat.DXF or status is not ProjectFileStatus.READY:
            raise AnalysisSourceNotReadyError('Текущий исходник проекта должен быть готовым DXF-файлом')

    @staticmethod
    def _ensure_job_matches(job: JobModel, project_id: int, project_file_id: int) -> None:
        if job.type is not JobType.ANALYZE:
            raise InvalidAnalysisError(f'Задача с id={job.id} не является задачей анализа')
        if job.project_id != project_id or job.project_file_id != project_file_id:
            raise InvalidAnalysisError(f'Задача с id={job.id} не соответствует проекту и исходному файлу')
        if job.status is not JobStatus.RUNNING:
            raise JobStateConflictError(job_id=job.id, status=job.status)
