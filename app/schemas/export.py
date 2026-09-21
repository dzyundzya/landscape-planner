from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import FileArtifactFormat, FileArtifactKind
from app.schemas.config_snapshot import CalculationConfigSnapshotSchema
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


class ExportJobInputSchema(BaseModel):
    """Полный снимок входов фоновой задачи экспорта."""

    export_schema_version: Annotated[int, Field(ge=1)] = 3
    draft: bool = False
    plan_id: Annotated[int, Field(ge=1)]
    plan_revision: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int, Field(ge=1)]
    project_file_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    config_snapshot_id: Annotated[int, Field(ge=1)]
    config: CalculationConfigSnapshotSchema
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
