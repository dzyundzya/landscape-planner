from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    CoordinateUnit,
    FileArtifactFormat,
    FileArtifactKind,
    NormativeRulesStatus,
    PlantCatalogStatus,
    TerritoryType,
)
from app.schemas.config_snapshot import BoundarySchema, LayerMappingSchema
from app.schemas.file_artifact import FileArtifactReadSchema
from app.schemas.plan import PlanGenerationSummarySchema
from app.schemas.plan_validation import PlanValidationReadSchema
from app.schemas.planting import PlantingReadSchema


class ExportPlanSnapshotSchema(BaseModel):
    """Данные ревизии плана, неизменно переданные задаче экспорта."""

    generator_version: str
    generation_summary: PlanGenerationSummarySchema
    plantings: list[PlantingReadSchema]

    model_config = ConfigDict(extra='forbid')


class ExportConfigSnapshotSchema(BaseModel):
    """Неизменяемая конфигурация, необходимая для формирования экспорта."""

    content_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    coordinate_unit: CoordinateUnit
    unit_scale_to_meters: Annotated[Decimal, Field(gt=0)]
    boundary: BoundarySchema
    layer_mappings: list[LayerMappingSchema]
    territory_type: TerritoryType
    rules_status: NormativeRulesStatus
    rules_version: Annotated[str, Field(min_length=1, max_length=100)]
    rules_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    plant_catalog_status: PlantCatalogStatus
    plant_catalog_version: Annotated[str, Field(min_length=1, max_length=100)]
    plant_catalog_sha256: Annotated[str, Field(min_length=64, max_length=64)]

    model_config = ConfigDict(extra='forbid')


class ExportJobInputSchema(BaseModel):
    """Полный снимок входов фоновой задачи экспорта."""

    export_schema_version: Annotated[int, Field(ge=1)] = 2
    plan_id: Annotated[int, Field(ge=1)]
    plan_revision: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int, Field(ge=1)]
    project_file_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    config_snapshot_id: Annotated[int, Field(ge=1)]
    config: ExportConfigSnapshotSchema
    plan: ExportPlanSnapshotSchema
    validation: PlanValidationReadSchema

    model_config = ConfigDict(extra='forbid')


class ExportManifestItemSchema(BaseModel):
    """Проверяемая запись файла в комплекте экспорта."""

    artifact_id: Annotated[int, Field(ge=1)]
    kind: FileArtifactKind
    format: FileArtifactFormat
    download_name: str
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(min_length=64, max_length=64)]

    model_config = ConfigDict(extra='forbid')


class ExportReadSchema(BaseModel):
    """Готовый неизменяемый комплект экспорта."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    plan_id: Annotated[int, Field(ge=1)]
    plan_revision: Annotated[int, Field(ge=1)]
    validation_id: Annotated[int, Field(ge=1)]
    job_id: Annotated[int, Field(ge=1)]
    export_version: str
    manifest: list[ExportManifestItemSchema]
    artifacts: list[FileArtifactReadSchema]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
