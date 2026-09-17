from datetime import UTC, datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobModel, JobStatus, JobType, PlanModel, PlanStatus, PlantingModel, PlantingSource, PlantingType
from app.planning import PlantingCandidate, validate_planting_set
from app.planning import PlantingValidationError as CorePlantingValidationError
from app.repositories.crud.analyses import AnalysisCRUDRepository
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.jobs import JobCRUDRepository
from app.repositories.crud.plans import PlanCRUDRepository
from app.repositories.crud.plantings import PlantingCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.schemas.config_snapshot import GenerationParametersSchema
from app.schemas.plan import PlanGenerationSummarySchema
from app.schemas.planting import PlantingCreateSchema
from app.services.base import BaseService
from app.services.exceptions.jobs import JobNotFoundError, JobStateConflictError
from app.services.exceptions.plans import InvalidPlanError, PlanNotFoundError, PlanPrerequisiteError
from app.services.exceptions.projects import ProjectNotFoundError
from app.services.jobs import JobService


class PlanService(BaseService[PlanCRUDRepository]):
    """Бизнес-логика генерации и чтения планов озеленения."""

    repository_class = PlanCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.analysis_repository = AnalysisCRUDRepository(async_session=async_session)
        self.config_repository = ConfigSnapshotCRUDRepository(async_session=async_session)
        self.job_repository = JobCRUDRepository(async_session=async_session)
        self.planting_repository = PlantingCRUDRepository(async_session=async_session)

    async def enqueue_plan_generation(self, project_id: int) -> JobModel:
        """Ставит генерацию плана по текущей конфигурации в очередь."""

        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        project_file = await self.project_file_repository.get_latest_for_project(project_id=project_id)
        if project_file is None:
            raise PlanPrerequisiteError(f'Project with id={project_id} has no source file')

        analysis = await self.analysis_repository.get_latest_for_project_file(project_file_id=project_file.id)
        if analysis is None:
            raise PlanPrerequisiteError(f'Project with id={project_id} has no analysis for the current source file')

        config = await self.config_repository.get_latest_for_project(project_id=project_id)
        if config is None or config.analysis_id != analysis.id:
            raise PlanPrerequisiteError(f'Project with id={project_id} has no config for the current analysis')

        active_job = await self.job_repository.get_active_plan_generation(
            project_id=project_id,
            config_snapshot_id=config.id,
        )
        if active_job is not None:
            return active_job

        return await JobService(async_session=self.session).enqueue_job(
            project_id=project_id,
            project_file_id=project_file.id,
            job_type=JobType.GENERATE_PLAN,
            input_data={
                'project_file_id': project_file.id,
                'project_file_version': project_file.version,
                'project_file_sha256': project_file.sha256,
                'analysis_id': analysis.id,
                'analysis_schema_version': analysis.schema_version,
                'config_snapshot_id': config.id,
                'config_version': config.version,
                'config_content_sha256': config.content_sha256,
                'rules_status': config.rules_status.value,
                'rules_version': config.rules_version,
                'rules_sha256': config.rules_sha256,
            },
        )

    async def get_plan(self, project_id: int, plan_id: int) -> PlanModel:
        """Возвращает план внутри заданного проекта."""

        plan = await self.repository.get_plan_for_project(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        return plan

    async def publish_plan(
        self,
        project_id: int,
        project_file_id: int,
        analysis_id: int,
        config_snapshot_id: int,
        job_id: int,
        generator_version: str,
        generation_summary: PlanGenerationSummarySchema,
        plantings: list[PlantingCreateSchema],
    ) -> PlanModel:
        """Атомарно публикует план и завершает задачу генерации."""

        existing_plan = await self.repository.get_by_job_id(job_id=job_id)
        if existing_plan is not None:
            return existing_plan

        normalized_generator_version = generator_version.strip()
        if not normalized_generator_version or len(normalized_generator_version) > 100:
            raise InvalidPlanError('Generator version must contain from 1 to 100 characters')

        job = await self.job_repository.get_job_by_id_for_update(job_id=job_id)
        if job is None:
            raise JobNotFoundError(job_id=job_id)
        self._ensure_job_matches(
            job=job,
            project_id=project_id,
            project_file_id=project_file_id,
            analysis_id=analysis_id,
            config_snapshot_id=config_snapshot_id,
        )

        config = await self.config_repository.get_obj_by_id(obj_id=config_snapshot_id)
        if config is None or config.project_id != project_id or config.analysis_id != analysis_id:
            raise InvalidPlanError(f'Config snapshot with id={config_snapshot_id} does not match plan inputs')
        self._validate_generation_result(
            summary=generation_summary,
            plantings=plantings,
            boundary=config.boundary,
            generation=config.generation,
        )

        analysis = await self.analysis_repository.get_obj_by_id(obj_id=analysis_id)
        if analysis is None or analysis.project_id != project_id or analysis.project_file_id != project_file_id:
            raise InvalidPlanError(f'Analysis with id={analysis_id} does not match plan inputs')

        plan = await self.repository.create_obj(
            new_obj=PlanModel(
                project_id=project_id,
                project_file_id=project_file_id,
                analysis_id=analysis_id,
                config_snapshot_id=config_snapshot_id,
                job_id=job_id,
                revision=1,
                status=PlanStatus.NEEDS_VERIFICATION,
                generator_version=normalized_generator_version,
                generation_summary=generation_summary.model_dump(mode='json'),
            )
        )
        await self.planting_repository.create_many(
            plantings=[
                PlantingModel(
                    plan_id=plan.id,
                    type=planting.type,
                    source=PlantingSource.GENERATED,
                    x_m=Decimal(str(planting.x_m)),
                    y_m=Decimal(str(planting.y_m)),
                    species=planting.species,
                )
                for planting in plantings
            ]
        )
        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = {'plan_id': plan.id, 'revision': plan.revision}
        job.error = None
        job.finished_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            'План опубликован: plan_id={}, project_id={}, config_id={}, revision={}',
            plan.id,
            project_id,
            config_snapshot_id,
            plan.revision,
        )
        return plan

    @staticmethod
    def _ensure_job_matches(
        job: JobModel,
        project_id: int,
        project_file_id: int,
        analysis_id: int,
        config_snapshot_id: int,
    ) -> None:
        if job.type is not JobType.GENERATE_PLAN:
            raise InvalidPlanError(f'Job with id={job.id} is not a plan generation job')
        expected_inputs = {
            'project_file_id': project_file_id,
            'analysis_id': analysis_id,
            'config_snapshot_id': config_snapshot_id,
        }
        if job.project_id != project_id or job.project_file_id != project_file_id:
            raise InvalidPlanError(f'Job with id={job.id} does not match project and source file')
        if any(job.input_data.get(key) != value for key, value in expected_inputs.items()):
            raise InvalidPlanError(f'Job with id={job.id} does not match analysis and config snapshot')
        if job.status is not JobStatus.RUNNING:
            raise JobStateConflictError(job_id=job.id, status=job.status)

    @staticmethod
    def _validate_generation_result(
        summary: PlanGenerationSummarySchema,
        plantings: list[PlantingCreateSchema],
        boundary: dict[str, object],
        generation: dict[str, object],
    ) -> None:
        parameters = GenerationParametersSchema.model_validate(generation)
        if summary.tree_count > parameters.max_trees:
            raise InvalidPlanError('Generated tree count exceeds config limit')
        if summary.bush_count > parameters.max_bushes:
            raise InvalidPlanError('Generated bush count exceeds config limit')
        tree_count = sum(planting.type is PlantingType.TREE for planting in plantings)
        bush_count = sum(planting.type is PlantingType.BUSH for planting in plantings)
        if tree_count != summary.tree_count or bush_count != summary.bush_count:
            raise InvalidPlanError('Generation summary does not match published plantings')
        try:
            validate_planting_set(
                candidates=[
                    PlantingCandidate(type=planting.type, x_m=planting.x_m, y_m=planting.y_m) for planting in plantings
                ],
                boundary=boundary,
                generation=generation,
            )
        except CorePlantingValidationError as exc:
            raise InvalidPlanError(str(exc)) from exc
