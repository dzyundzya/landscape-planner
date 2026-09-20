from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cad import analyze_dxf
from app.models import JobModel, ProjectFileFormat, ProjectFileStatus
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.services.analyses import ANALYSIS_SCHEMA_VERSION, AnalysisService
from app.services.exceptions.analyses import InvalidAnalysisError
from app.services.jobs import JobService
from app.storage import LocalFileStorage
from app.worker.dispatcher import OwnershipGuard
from app.worker.metrics import run_measured_operation


class AnalysisJobHandler:
    """Выполняет анализ зафиксированной версии исходного DXF."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: LocalFileStorage,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        project_file_id = self._get_project_file_id(job=job)
        async with self.session_factory() as session:
            project_file = await ProjectFileCRUDRepository(session).get_obj_by_id(obj_id=project_file_id)
            if project_file is None or project_file.project_id != job.project_id:
                raise InvalidAnalysisError('Источник анализа не соответствует поставленной задаче')
            if project_file.format is not ProjectFileFormat.DXF or project_file.status is not ProjectFileStatus.READY:
                raise InvalidAnalysisError('Источник анализа должен быть готовым DXF-файлом')
            self._validate_snapshot(job=job, source_sha256=project_file.sha256, source_version=project_file.version)
            storage_key = project_file.storage_key
            await JobService(session).update_stage(job_id=job.id, stage='analyzing_dxf')

        source_path = self.storage.get_path(storage_key)
        result = await run_measured_operation(
            partial(analyze_dxf, source_path),
            job_id=job.id,
            operation_name='analyze_dxf',
            source_path=source_path,
        )
        await ensure_ownership()

        async with self.session_factory() as session:
            await AnalysisService(session).publish_analysis(
                project_id=job.project_id,
                project_file_id=project_file_id,
                job_id=job.id,
                result=result,
            )

    @staticmethod
    def _get_project_file_id(job: JobModel) -> int:
        if job.project_file_id is None:
            raise InvalidAnalysisError('У задачи анализа отсутствует исходный файл')
        return job.project_file_id

    @staticmethod
    def _validate_snapshot(job: JobModel, source_sha256: str, source_version: int) -> None:
        expected = {
            'project_file_id': job.project_file_id,
            'project_file_version': source_version,
            'project_file_sha256': source_sha256,
            'analysis_schema_version': ANALYSIS_SCHEMA_VERSION,
        }
        if any(job.input_data.get(key) != value for key, value in expected.items()):
            raise InvalidAnalysisError('Снимок источника анализа не соответствует поставленной задаче')
