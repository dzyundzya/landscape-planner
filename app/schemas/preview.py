from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models import PlantingType, SemanticObjectType
from app.schemas.planting import PlantingReadSchema

GeoJsonGeometry = dict[str, JsonValue]


class PreviewObjectSchema(BaseModel):
    """Подтверждённый объект исходного DXF в локальных метрах."""

    source_object_id: Annotated[str, Field(min_length=1, max_length=500)]
    object_type: SemanticObjectType
    geometry: GeoJsonGeometry

    model_config = ConfigDict(extra='forbid')


class PreviewRestrictionSchema(BaseModel):
    """Отдельная нормативная зона с происхождением ограничения."""

    source_object_id: Annotated[str, Field(min_length=1, max_length=500)]
    object_type: SemanticObjectType
    planting_type: PlantingType
    rule_id: Annotated[str, Field(min_length=1, max_length=100)]
    rule_version: Annotated[str, Field(min_length=1, max_length=100)]
    min_distance_m: Annotated[float, Field(gt=0)]
    document: str
    clause: str
    geometry: GeoJsonGeometry

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class PreviewZonesSchema(BaseModel):
    """Объединённые допустимые и запрещённые зоны двух типов посадок."""

    tree_available: GeoJsonGeometry
    bush_available: GeoJsonGeometry
    tree_exclusion: GeoJsonGeometry
    bush_exclusion: GeoJsonGeometry

    model_config = ConfigDict(extra='forbid')


class PreviewIssueSchema(BaseModel):
    """Диагностическая проблема полноты preview."""

    code: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    source_object_id: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    planting_type: PlantingType | None = None
    rule_id: Annotated[str | None, Field(min_length=1, max_length=100)] = None

    model_config = ConfigDict(extra='forbid')


class PreviewSummarySchema(BaseModel):
    """Сводка полноты облегчённой геометрии для браузера."""

    object_count: Annotated[int, Field(ge=0)]
    displayed_object_count: Annotated[int, Field(ge=0)]
    restriction_count: Annotated[int, Field(ge=0)]
    displayed_restriction_count: Annotated[int, Field(ge=0)]
    source_coordinate_count: Annotated[int, Field(ge=0)]
    displayed_coordinate_count: Annotated[int, Field(ge=0)]
    simplified: bool

    model_config = ConfigDict(extra='forbid')


class PlanPreviewGeometrySchema(BaseModel):
    """Статическая геометрия, рассчитанная worker для плана."""

    schema_version: Annotated[int, Field(ge=1)] = 2
    coordinate_space: Literal['local_meters'] = 'local_meters'
    boundary: GeoJsonGeometry
    objects: list[PreviewObjectSchema]
    restrictions: list[PreviewRestrictionSchema]
    zones: PreviewZonesSchema
    issues: list[PreviewIssueSchema]
    summary: PreviewSummarySchema | None = None

    model_config = ConfigDict(extra='forbid')


class PlanPreviewReadSchema(PlanPreviewGeometrySchema):
    """Диагностическое представление текущей ревизии плана."""

    plan_id: Annotated[int, Field(ge=1)]
    plan_revision: Annotated[int, Field(ge=1)]
    plantings: list[PlantingReadSchema]
