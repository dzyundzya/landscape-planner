from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from shapely.geometry import LineString, Polygon, shape
from shapely.geometry.base import BaseGeometry

from app.domain import CoordinateTransform, GeometryProvenance, NormalizationResult


class GeometryRole(StrEnum):
    """Подтверждённый способ интерпретации геометрии слоя."""

    LINE = 'line'
    AREA = 'area'


@dataclass(frozen=True, slots=True)
class ConfirmedLayerMapping:
    """Подтверждённая семантика одного слоя DXF."""

    layer: str
    object_type: str
    geometry_role: GeometryRole


@dataclass(frozen=True, slots=True)
class ProjectGeometryIssue:
    """Проблема, препятствующая полному построению геометрии проекта."""

    code: str
    message: str
    source_object_id: str | None = None
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class PreparedGeometryObject:
    """Классифицированный Shapely-объект в локальных метрах."""

    object_type: str
    geometry: BaseGeometry
    provenance: GeometryProvenance
    min_z_m: float
    max_z_m: float


@dataclass(frozen=True, slots=True)
class PreparedProjectGeometry:
    """Подтверждённая граница, препятствия и диагностические проблемы."""

    boundary: BaseGeometry
    objects: tuple[PreparedGeometryObject, ...]
    transform: CoordinateTransform
    unmapped_layers: tuple[str, ...]
    issues: tuple[ProjectGeometryIssue, ...]

    @property
    def is_complete(self) -> bool:
        """Показывает отсутствие блокирующих проблем подготовки."""

        return not any(issue.blocking for issue in self.issues)


class ProjectGeometryError(Exception):
    """Подтверждённая конфигурация геометрии некорректна."""


def prepare_project_geometry(
    normalization: NormalizationResult,
    unit_scale_to_meters: Decimal | float,
    boundary: dict[str, object],
    layer_mappings: Iterable[dict[str, object]],
) -> PreparedProjectGeometry:
    """Применяет подтверждённую конфигурацию к нормализованным объектам DXF."""

    scale = float(unit_scale_to_meters)
    if not isfinite(scale) or scale <= 0:
        raise ProjectGeometryError('Unit scale to meters must be finite and positive')
    transform = CoordinateTransform(scale_to_meters=scale)
    boundary_geometry = _build_boundary(boundary=boundary)
    mappings = _build_mapping_index(layer_mappings=layer_mappings)
    issues = [
        ProjectGeometryIssue(
            code=issue.code,
            message=issue.message,
            source_object_id=issue.source_object_id,
        )
        for issue in normalization.issues
    ]
    objects = []
    unmapped_layers = set()

    for normalized in normalization.geometries:
        mapping = mappings.get(normalized.provenance.layer.casefold())
        if mapping is None:
            unmapped_layers.add(normalized.provenance.layer)
            continue
        if mapping.object_type == 'ignore':
            continue

        coordinates = [transform.to_local_meters(point) for point in normalized.points]
        geometry, issue = _build_geometry(
            coordinates=coordinates,
            closed=normalized.closed,
            role=mapping.geometry_role,
            source_object_id=normalized.provenance.source_object_id,
        )
        if issue is not None:
            issues.append(issue)
            continue
        if geometry is None:
            continue
        objects.append(
            PreparedGeometryObject(
                object_type=mapping.object_type,
                geometry=geometry,
                provenance=normalized.provenance,
                min_z_m=normalized.provenance.min_z * scale,
                max_z_m=normalized.provenance.max_z * scale,
            )
        )

    for layer in sorted(unmapped_layers, key=str.casefold):
        issues.append(
            ProjectGeometryIssue(
                code='unmapped_layer',
                message=f'Layer {layer} has geometry but no confirmed semantic mapping',
            )
        )

    return PreparedProjectGeometry(
        boundary=boundary_geometry,
        objects=tuple(objects),
        transform=transform,
        unmapped_layers=tuple(sorted(unmapped_layers, key=str.casefold)),
        issues=tuple(issues),
    )


def _build_boundary(boundary: dict[str, object]) -> BaseGeometry:
    try:
        geometry = shape(boundary)
    except (TypeError, ValueError, KeyError) as exc:
        raise ProjectGeometryError('Configured project boundary cannot be read') from exc
    if geometry.geom_type not in {'Polygon', 'MultiPolygon'} or geometry.is_empty or not geometry.is_valid:
        raise ProjectGeometryError('Configured project boundary is invalid')
    return geometry


def _build_mapping_index(layer_mappings: Iterable[dict[str, object]]) -> dict[str, ConfirmedLayerMapping]:
    mappings = {}
    for raw_mapping in layer_mappings:
        layer = raw_mapping.get('layer')
        object_type = raw_mapping.get('object_type')
        attributes = raw_mapping.get('attributes', {})
        if not isinstance(layer, str) or not layer.strip() or not isinstance(object_type, str):
            raise ProjectGeometryError('Layer mapping has invalid layer or object type')
        if not isinstance(attributes, dict):
            raise ProjectGeometryError(f'Layer mapping attributes are invalid for layer {layer}')
        try:
            geometry_role = GeometryRole(attributes.get('geometry_role', GeometryRole.LINE))
        except ValueError as exc:
            raise ProjectGeometryError(f'Layer {layer} has invalid geometry role') from exc
        key = layer.casefold()
        if key in mappings:
            raise ProjectGeometryError(f'Layer {layer} has duplicate semantic mappings')
        mappings[key] = ConfirmedLayerMapping(
            layer=layer,
            object_type=object_type,
            geometry_role=geometry_role,
        )
    return mappings


def _build_geometry(
    coordinates,
    closed: bool,
    role: GeometryRole,
    source_object_id: str,
) -> tuple[BaseGeometry | None, ProjectGeometryIssue | None]:
    xy = [(point.x, point.y) for point in coordinates]
    if role is GeometryRole.AREA:
        if not closed:
            return None, ProjectGeometryIssue(
                code='open_area_geometry',
                message='Geometry confirmed as area is not closed',
                source_object_id=source_object_id,
            )
        geometry: BaseGeometry = Polygon(xy)
    else:
        geometry = LineString(xy)

    if geometry.is_empty or not geometry.is_valid:
        return None, ProjectGeometryIssue(
            code='invalid_prepared_geometry',
            message='Geometry is empty or invalid after conversion to local meters',
            source_object_id=source_object_id,
        )
    if (role is GeometryRole.AREA and geometry.area <= 0) or (role is GeometryRole.LINE and geometry.length <= 0):
        return None, ProjectGeometryIssue(
            code='degenerate_prepared_geometry',
            message='Geometry has zero area or length after conversion to local meters',
            source_object_id=source_object_id,
        )
    return geometry, None
