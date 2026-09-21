from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cad import normalize_dxf
from app.domain import NormalizationOptions
from app.geometry import build_restriction_zones, prepare_project_geometry
from app.models import JobModel, ProjectFileFormat, ProjectFileStatus, TerritoryType
from app.planning import (
    ValidationPlanting,
    assign_species,
    build_plan_preview,
    generate_plantings,
    validate_plan_geometry,
)
from app.repositories.crud.analyses import AnalysisCRUDRepository
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.rules import load_plant_catalog, load_rule_set
from app.schemas.config_snapshot import GenerationParametersSchema
from app.schemas.plan import PlanGenerationSummarySchema
from app.schemas.plan_validation import PlanValidationPublishSchema
from app.schemas.planting import PlantingCreateSchema
from app.schemas.preview import PlanPreviewGeometrySchema
from app.services.exceptions.plans import InvalidPlanError
from app.services.jobs import JobService
from app.services.plans import PlanService
from app.storage import LocalFileStorage
from app.worker.dispatcher import OwnershipGuard
from app.worker.metrics import run_measured_operation


@dataclass(frozen=True, slots=True)
class _PlanGenerationInput:
    """Неизменяемые входы тяжёлой части генерации."""

    source_path: Path
    unit_scale_to_meters: float
    boundary: dict[str, object]
    layer_mappings: list[dict[str, object]]
    generation: dict[str, object]
    rules_version: str
    rules_sha256: str
    territory_type: TerritoryType
    plant_catalog_version: str
    plant_catalog_sha256: str


@dataclass(frozen=True, slots=True)
class _PlanGenerationOutput:
    """Подготовленный результат генератора и независимой проверки."""

    generator_version: str
    summary: PlanGenerationSummarySchema
    plantings: list[PlantingCreateSchema]
    planting_ids: list[UUID]
    validation: PlanValidationPublishSchema
    preview: PlanPreviewGeometrySchema


class PlanGenerationJobHandler:
    """Выполняет полный расчёт плана по зафиксированным входам задачи."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: LocalFileStorage,
        rules_path: Path,
        plant_catalog_path: Path,
        curve_tolerance_m: float,
        preview_simplify_tolerance_m: float,
        preview_max_objects: int,
        preview_max_restrictions: int,
        preview_max_coordinates: int,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.rules_path = rules_path
        self.plant_catalog_path = plant_catalog_path
        self.curve_tolerance_m = curve_tolerance_m
        self.preview_simplify_tolerance_m = preview_simplify_tolerance_m
        self.preview_max_objects = preview_max_objects
        self.preview_max_restrictions = preview_max_restrictions
        self.preview_max_coordinates = preview_max_coordinates

    async def execute(self, job: JobModel, ensure_ownership: OwnershipGuard) -> None:
        async with self.session_factory() as session:
            generation_input = await self._load_input(session=session, job=job)
            await JobService(session).update_stage(job_id=job.id, stage='generating_plan')

        output = await run_measured_operation(
            partial(self._generate, generation_input),
            job_id=job.id,
            operation_name='generate_plan',
            source_path=generation_input.source_path,
        )
        await ensure_ownership()

        async with self.session_factory() as session:
            await PlanService(session).publish_plan(
                project_id=job.project_id,
                project_file_id=self._required_int(job=job, key='project_file_id'),
                analysis_id=self._required_int(job=job, key='analysis_id'),
                config_snapshot_id=self._required_int(job=job, key='config_snapshot_id'),
                job_id=job.id,
                generator_version=output.generator_version,
                generation_summary=output.summary,
                plantings=output.plantings,
                planting_ids=output.planting_ids,
                validation_data=output.validation,
                preview_geometry=output.preview,
            )

    async def _load_input(self, session: AsyncSession, job: JobModel) -> _PlanGenerationInput:
        project_file_id = self._required_int(job=job, key='project_file_id')
        analysis_id = self._required_int(job=job, key='analysis_id')
        config_snapshot_id = self._required_int(job=job, key='config_snapshot_id')

        project_file = await ProjectFileCRUDRepository(session).get_obj_by_id(obj_id=project_file_id)
        analysis = await AnalysisCRUDRepository(session).get_obj_by_id(obj_id=analysis_id)
        config = await ConfigSnapshotCRUDRepository(session).get_obj_by_id(obj_id=config_snapshot_id)
        if project_file is None or project_file.project_id != job.project_id:
            raise InvalidPlanError('Исходный файл генерации не соответствует поставленной задаче')
        if project_file.format is not ProjectFileFormat.DXF or project_file.status is not ProjectFileStatus.READY:
            raise InvalidPlanError('Для генерации требуется готовый DXF-файл')
        if analysis is None or analysis.project_id != job.project_id or analysis.project_file_id != project_file.id:
            raise InvalidPlanError('Анализ генерации не соответствует исходному файлу')
        if config is None or config.project_id != job.project_id or config.analysis_id != analysis.id:
            raise InvalidPlanError('Конфигурация генерации не соответствует анализу')

        expected = {
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
            'territory_type': config.territory_type.value if config.territory_type else None,
            'plant_catalog_status': config.plant_catalog_status.value if config.plant_catalog_status else None,
            'plant_catalog_version': config.plant_catalog_version,
            'plant_catalog_sha256': config.plant_catalog_sha256,
        }
        if any(job.input_data.get(key) != value for key, value in expected.items()):
            raise InvalidPlanError('Снимок входов генерации не соответствует поставленной задаче')
        if config.rules_version is None or config.rules_sha256 is None:
            raise InvalidPlanError('В конфигурации отсутствует снимок нормативного справочника')
        if config.territory_type is None or config.plant_catalog_version is None or config.plant_catalog_sha256 is None:
            raise InvalidPlanError('В конфигурации отсутствует снимок справочника растений')

        return _PlanGenerationInput(
            source_path=self.storage.get_path(project_file.storage_key),
            unit_scale_to_meters=float(config.unit_scale_to_meters),
            boundary=config.boundary,
            layer_mappings=config.layer_mappings,
            generation=config.generation,
            rules_version=config.rules_version,
            rules_sha256=config.rules_sha256,
            territory_type=config.territory_type,
            plant_catalog_version=config.plant_catalog_version,
            plant_catalog_sha256=config.plant_catalog_sha256,
        )

    def _generate(self, data: _PlanGenerationInput) -> _PlanGenerationOutput:
        rule_set = load_rule_set(self.rules_path)
        if rule_set.data.version != data.rules_version or rule_set.sha256 != data.rules_sha256:
            raise InvalidPlanError('Нормативный справочник изменился после сохранения конфигурации')
        plant_catalog = load_plant_catalog(self.plant_catalog_path)
        if (
            plant_catalog.data.version != data.plant_catalog_version
            or plant_catalog.sha256 != data.plant_catalog_sha256
        ):
            raise InvalidPlanError('Справочник растений изменился после сохранения конфигурации')

        source_tolerance = self.curve_tolerance_m / data.unit_scale_to_meters
        normalization = normalize_dxf(
            data.source_path,
            options=NormalizationOptions(curve_tolerance=source_tolerance),
        )
        project = prepare_project_geometry(
            normalization=normalization,
            unit_scale_to_meters=data.unit_scale_to_meters,
            boundary=data.boundary,
            layer_mappings=data.layer_mappings,
        )
        parameters = GenerationParametersSchema.model_validate(data.generation)
        restrictions = build_restriction_zones(project=project, rule_set=rule_set, parameters=parameters)
        result = generate_plantings(restrictions=restrictions, parameters=parameters)
        species = assign_species(
            planting_types=(planting.type for planting in result.plantings),
            catalog=plant_catalog,
            territory_type=data.territory_type,
        )

        planting_ids = [uuid4() for _ in result.plantings]
        plantings = [
            PlantingCreateSchema(
                type=planting.type,
                x_m=planting.x_m,
                y_m=planting.y_m,
                species=plant_name,
            )
            for planting, plant_name in zip(result.plantings, species, strict=True)
        ]
        validation = validate_plan_geometry(
            project=project,
            restrictions=restrictions,
            plantings=[
                ValidationPlanting(
                    public_id=public_id,
                    type=planting.type,
                    x_m=planting.x_m,
                    y_m=planting.y_m,
                )
                for public_id, planting in zip(planting_ids, result.plantings, strict=True)
            ],
            parameters=parameters,
        )
        preview = build_plan_preview(
            project=project,
            restrictions=restrictions,
            simplify_tolerance_m=self.preview_simplify_tolerance_m,
            max_objects=self.preview_max_objects,
            max_restrictions=self.preview_max_restrictions,
            max_coordinates=self.preview_max_coordinates,
        )
        return _PlanGenerationOutput(
            generator_version=result.generator_version,
            summary=PlanGenerationSummarySchema(
                candidate_count=result.candidate_count,
                tree_count=result.tree_count,
                bush_count=result.bush_count,
                rejected_candidate_count=result.rejected_candidate_count,
                strategy='hex_grid_greedy',
                selected_offset_index=result.selected_offset_index,
                offset_x_m=result.offset_x_m,
                offset_y_m=result.offset_y_m,
                grid_spacing_m=result.grid_spacing_m,
                warnings=list(result.warnings),
            ),
            plantings=plantings,
            planting_ids=planting_ids,
            validation=validation,
            preview=preview,
        )

    @staticmethod
    def _required_int(job: JobModel, key: str) -> int:
        value = job.input_data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidPlanError(f'В задаче генерации отсутствует корректное поле {key}')
        return value
