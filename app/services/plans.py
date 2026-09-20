from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

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
from app.schemas.plan_validation import PlanValidationPublishSchema
from app.schemas.planting import PlantingCreateSchema
from app.schemas.preview import PlanPreviewGeometrySchema, PlanPreviewReadSchema
from app.services.base import BaseService
from app.services.exceptions.jobs import JobNotFoundError, JobStateConflictError
from app.services.exceptions.plans import (
    CurrentPlanNotFoundError,
    InvalidPlanError,
    PlanNotFoundError,
    PlanPrerequisiteError,
    PlanPreviewUnavailableError,
)
from app.services.exceptions.projects import ProjectNotFoundError
from app.services.jobs import JobService
from app.services.plan_validations import PlanValidationService


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
            raise PlanPrerequisiteError(f'У проекта с id={project_id} отсутствует исходный файл')

        analysis = await self.analysis_repository.get_latest_for_project_file(project_file_id=project_file.id)
        if analysis is None:
            raise PlanPrerequisiteError(f'У проекта с id={project_id} отсутствует анализ текущего исходного файла')

        config = await self.config_repository.get_latest_for_project(project_id=project_id)
        if config is None or config.analysis_id != analysis.id:
            raise PlanPrerequisiteError(f'У проекта с id={project_id} отсутствует конфигурация текущего анализа')
        if (
            config.territory_type is None
            or config.plant_catalog_status is None
            or config.plant_catalog_version is None
            or config.plant_catalog_sha256 is None
        ):
            raise PlanPrerequisiteError('Сохраните новую конфигурацию с выбранным типом территории')

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
                'territory_type': config.territory_type.value,
                'plant_catalog_status': config.plant_catalog_status.value,
                'plant_catalog_version': config.plant_catalog_version,
                'plant_catalog_sha256': config.plant_catalog_sha256,
            },
        )

    async def get_plan(self, project_id: int, plan_id: int) -> PlanModel:
        """Возвращает план внутри заданного проекта."""

        plan = await self.repository.get_plan_for_project(plan_id=plan_id, project_id=project_id)
        if plan is None:
            raise PlanNotFoundError(plan_id=plan_id)
        return plan

    async def get_current_plan(self, project_id: int) -> PlanModel:
        """Возвращает последний план текущей конфигурации проекта."""

        if await self.project_repository.get_obj_by_id(obj_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)
        project_file = await self.project_file_repository.get_latest_for_project(project_id=project_id)
        analysis = (
            await self.analysis_repository.get_latest_for_project_file(project_file_id=project_file.id)
            if project_file is not None
            else None
        )
        config = await self.config_repository.get_latest_for_project(project_id=project_id)
        if analysis is None or config is None or config.analysis_id != analysis.id:
            raise CurrentPlanNotFoundError(project_id=project_id)
        plan = await self.repository.get_latest_for_config(
            project_id=project_id,
            config_snapshot_id=config.id,
        )
        if plan is None:
            raise CurrentPlanNotFoundError(project_id=project_id)
        return plan

    async def get_preview(self, project_id: int, plan_id: int) -> PlanPreviewReadSchema:
        """Возвращает подготовленную геометрию и посадки текущей ревизии."""

        plan = await self.get_plan(project_id=project_id, plan_id=plan_id)
        if plan.preview_geometry is None:
            raise PlanPreviewUnavailableError(plan_id=plan.id)
        geometry = PlanPreviewGeometrySchema.model_validate(plan.preview_geometry)
        return PlanPreviewReadSchema(
            **geometry.model_dump(mode='python'),
            plan_id=plan.id,
            plan_revision=plan.revision,
            plantings=plan.plantings,
        )

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
        planting_ids: list[UUID] | None = None,
        validation_data: PlanValidationPublishSchema | None = None,
        preview_geometry: PlanPreviewGeometrySchema | None = None,
    ) -> PlanModel:
        """Атомарно публикует план и завершает задачу генерации."""

        existing_plan = await self.repository.get_by_job_id(job_id=job_id)
        if existing_plan is not None:
            return existing_plan

        normalized_generator_version = generator_version.strip()
        if not normalized_generator_version or len(normalized_generator_version) > 100:
            raise InvalidPlanError('Версия генератора должна содержать от 1 до 100 символов')

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
            raise InvalidPlanError(f'Снимок конфигурации с id={config_snapshot_id} не соответствует входам плана')
        self._validate_generation_result(
            summary=generation_summary,
            plantings=plantings,
            boundary=config.boundary,
            generation=config.generation,
        )
        self._validate_atomic_validation_inputs(
            plantings=plantings,
            planting_ids=planting_ids,
            validation_data=validation_data,
        )

        analysis = await self.analysis_repository.get_obj_by_id(obj_id=analysis_id)
        if analysis is None or analysis.project_id != project_id or analysis.project_file_id != project_file_id:
            raise InvalidPlanError(f'Анализ с id={analysis_id} не соответствует входам плана')

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
                preview_geometry=preview_geometry.model_dump(mode='json') if preview_geometry is not None else None,
            )
        )
        planting_models = self._build_planting_models(
            plan_id=plan.id,
            plantings=plantings,
            planting_ids=planting_ids,
        )
        await self.planting_repository.create_many(plantings=planting_models)
        validation = None
        if validation_data is not None:
            validation = await PlanValidationService(self.session).create_validation_for_plan(
                plan=plan,
                data=validation_data,
                planting_ids={planting.public_id for planting in planting_models},
            )
        job.status = JobStatus.SUCCEEDED
        job.stage = 'completed'
        job.result = {'plan_id': plan.id, 'revision': plan.revision}
        if validation is not None:
            job.result['validation_id'] = validation.id
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
    def _validate_atomic_validation_inputs(
        plantings: list[PlantingCreateSchema],
        planting_ids: list[UUID] | None,
        validation_data: PlanValidationPublishSchema | None,
    ) -> None:
        if (planting_ids is None) != (validation_data is None):
            raise InvalidPlanError('ID посадок и результат валидатора должны передаваться вместе')
        if planting_ids is not None:
            if len(planting_ids) != len(plantings):
                raise InvalidPlanError('Количество ID посадок не соответствует результату генератора')
            if len(planting_ids) != len(set(planting_ids)):
                raise InvalidPlanError('ID сгенерированных посадок не должны повторяться')

    @staticmethod
    def _build_planting_models(
        plan_id: int,
        plantings: list[PlantingCreateSchema],
        planting_ids: list[UUID] | None,
    ) -> list[PlantingModel]:
        models = []
        for index, planting in enumerate(plantings):
            model = PlantingModel(
                plan_id=plan_id,
                type=planting.type,
                source=PlantingSource.GENERATED,
                x_m=Decimal(str(planting.x_m)),
                y_m=Decimal(str(planting.y_m)),
                species=planting.species,
            )
            if planting_ids is not None:
                model.public_id = planting_ids[index]
            models.append(model)
        return models

    @staticmethod
    def _ensure_job_matches(
        job: JobModel,
        project_id: int,
        project_file_id: int,
        analysis_id: int,
        config_snapshot_id: int,
    ) -> None:
        if job.type is not JobType.GENERATE_PLAN:
            raise InvalidPlanError(f'Задача с id={job.id} не является задачей генерации плана')
        expected_inputs = {
            'project_file_id': project_file_id,
            'analysis_id': analysis_id,
            'config_snapshot_id': config_snapshot_id,
        }
        if job.project_id != project_id or job.project_file_id != project_file_id:
            raise InvalidPlanError(f'Задача с id={job.id} не соответствует проекту и исходному файлу')
        if any(job.input_data.get(key) != value for key, value in expected_inputs.items()):
            raise InvalidPlanError(f'Задача с id={job.id} не соответствует анализу и снимку конфигурации')
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
            raise InvalidPlanError('Количество сгенерированных деревьев превышает лимит конфигурации')
        if summary.bush_count > parameters.max_bushes:
            raise InvalidPlanError('Количество сгенерированных кустарников превышает лимит конфигурации')
        tree_count = sum(planting.type is PlantingType.TREE for planting in plantings)
        bush_count = sum(planting.type is PlantingType.BUSH for planting in plantings)
        if tree_count != summary.tree_count or bush_count != summary.bush_count:
            raise InvalidPlanError('Сводка генерации не соответствует опубликованным посадкам')
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
