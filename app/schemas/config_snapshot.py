from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.models import CoordinateUnit, NormativeRulesStatus, SemanticObjectType

Coordinate = tuple[float, float]
LinearRing = Annotated[list[Coordinate], Field(min_length=4)]
PolygonCoordinates = Annotated[list[LinearRing], Field(min_length=1)]


def validate_polygon_coordinates(coordinates: list[list[Coordinate]]) -> None:
    """Проверяет замкнутость и минимальный состав колец полигона."""

    for ring in coordinates:
        if ring[0] != ring[-1]:
            raise ValueError('Boundary rings must be closed')
        if len(set(ring[:-1])) < 3:
            raise ValueError('Boundary rings must contain at least three distinct points')


class PolygonBoundarySchema(BaseModel):
    """Граница участка в виде полигона с возможными отверстиями."""

    type: Literal['Polygon']
    coordinate_space: Literal['local_meters'] = 'local_meters'
    coordinates: PolygonCoordinates

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_rings(self) -> 'PolygonBoundarySchema':
        """Проверяет кольца полигона."""

        validate_polygon_coordinates(self.coordinates)
        return self


class MultiPolygonBoundarySchema(BaseModel):
    """Граница участка из нескольких полигонов."""

    type: Literal['MultiPolygon']
    coordinate_space: Literal['local_meters'] = 'local_meters'
    coordinates: Annotated[list[PolygonCoordinates], Field(min_length=1)]

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_polygons(self) -> 'MultiPolygonBoundarySchema':
        """Проверяет кольца всех полигонов."""

        for polygon in self.coordinates:
            validate_polygon_coordinates(polygon)
        return self


BoundarySchema = Annotated[PolygonBoundarySchema | MultiPolygonBoundarySchema, Field(discriminator='type')]


class LayerMappingSchema(BaseModel):
    """Подтверждённая классификация объектов слоя DXF."""

    layer: Annotated[str, Field(min_length=1, max_length=255)]
    object_type: SemanticObjectType
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class GenerationParametersSchema(BaseModel):
    """Проектные параметры генерации посадок."""

    max_trees: Annotated[int, Field(ge=0, le=10_000)]
    max_bushes: Annotated[int, Field(ge=0, le=10_000)]
    tree_tree_distance_m: Annotated[float, Field(gt=0, le=1000)]
    bush_bush_distance_m: Annotated[float, Field(gt=0, le=1000)]
    tree_bush_distance_m: Annotated[float, Field(gt=0, le=1000)]
    grid_spacing_m: Annotated[float, Field(gt=0, le=1000)]

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ConfigSnapshotUpsertSchema(BaseModel):
    """Схема подтверждения настроек текущего анализа."""

    coordinate_unit: CoordinateUnit
    boundary: BoundarySchema
    layer_mappings: list[LayerMappingSchema] = Field(default_factory=list)
    generation: GenerationParametersSchema

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_unique_layers(self) -> 'ConfigSnapshotUpsertSchema':
        """Запрещает несколько классификаций одного слоя."""

        normalized_layers = [mapping.layer.casefold() for mapping in self.layer_mappings]
        if len(normalized_layers) != len(set(normalized_layers)):
            raise ValueError('Each DXF layer may have only one mapping')
        return self


class ConfigSnapshotReadSchema(BaseModel):
    """Схема неизменяемого снимка настроек проекта."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    analysis_id: Annotated[int, Field(ge=1)]
    version: Annotated[int, Field(ge=1)]
    schema_version: Annotated[int, Field(ge=1)]
    coordinate_unit: CoordinateUnit
    unit_scale_to_meters: Decimal
    boundary: BoundarySchema
    layer_mappings: list[LayerMappingSchema]
    generation: GenerationParametersSchema
    rules_status: NormativeRulesStatus
    rules_version: str | None
    rules_sha256: Annotated[str | None, Field(min_length=64, max_length=64)]
    content_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
