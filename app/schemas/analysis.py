from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import AnalysisWarningSeverity

NonNegativeInt = Annotated[int, Field(ge=0)]


class AnalysisBoundsSchema(BaseModel):
    """Прямоугольные границы обнаруженной геометрии."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_order(self) -> 'AnalysisBoundsSchema':
        """Проверяет порядок минимальных и максимальных координат."""

        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError('Analysis bounds minimum must not exceed maximum')
        return self


class AnalysisLayerSchema(BaseModel):
    """Сводка объектов одного слоя DXF."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    entity_count: NonNegativeInt
    entity_counts: dict[str, NonNegativeInt] = Field(default_factory=dict)

    model_config = ConfigDict(extra='forbid')


class AnalysisWarningSchema(BaseModel):
    """Структурированное предупреждение анализатора."""

    code: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    severity: AnalysisWarningSeverity

    model_config = ConfigDict(extra='forbid')


class AnalysisResultSchema(BaseModel):
    """Версионированный результат разбора DXF."""

    dxf_version: Annotated[str | None, Field(max_length=32)] = None
    drawing_units: Annotated[str | None, Field(max_length=64)] = None
    entity_counts: dict[str, NonNegativeInt] = Field(default_factory=dict)
    layers: list[AnalysisLayerSchema] = Field(default_factory=list)
    blocks: dict[str, NonNegativeInt] = Field(default_factory=dict)
    labels_count: NonNegativeInt = 0
    external_references: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(default_factory=list)
    unsupported_entities: dict[str, NonNegativeInt] = Field(default_factory=dict)
    bounds: AnalysisBoundsSchema | None = None
    warnings: list[AnalysisWarningSchema] = Field(default_factory=list)
    requires_user_confirmation: bool = True

    model_config = ConfigDict(extra='forbid')


class AnalysisReadSchema(BaseModel):
    """Схема сохранённого анализа проекта."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int, Field(ge=1)]
    job_id: Annotated[int, Field(ge=1)]
    schema_version: Annotated[int, Field(ge=1)]
    result: AnalysisResultSchema
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
