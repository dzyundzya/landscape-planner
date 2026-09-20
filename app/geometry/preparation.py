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
    attributes: dict[str, object]


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
    attributes: dict[str, object]
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
        raise ProjectGeometryError('Масштаб перевода в метры должен быть конечным и положительным')
    transform = CoordinateTransform(scale_to_meters=scale)
    boundary_geometry = _build_boundary(boundary=boundary)
    mappings = _build_mapping_index(layer_mappings=layer_mappings)
    issues = _build_normalization_issues(normalization=normalization)
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
                attributes=dict(mapping.attributes),
                min_z_m=normalized.provenance.min_z * scale,
                max_z_m=normalized.provenance.max_z * scale,
            )
        )

    for layer in sorted(unmapped_layers, key=str.casefold):
        issues.append(
            ProjectGeometryIssue(
                code='unmapped_layer',
                message=f'Слой {layer} содержит геометрию, но не имеет подтверждённого смыслового назначения',
            )
        )

    return PreparedProjectGeometry(
        boundary=boundary_geometry,
        objects=tuple(objects),
        transform=transform,
        unmapped_layers=tuple(sorted(unmapped_layers, key=str.casefold)),
        issues=tuple(issues),
    )


def _build_normalization_issues(normalization: NormalizationResult) -> list[ProjectGeometryIssue]:
    grouped: dict[tuple[str, str], list[str | None]] = {}
    for issue in normalization.issues:
        grouped.setdefault((issue.code, issue.message), []).append(issue.source_object_id)

    result = []
    for (code, message), source_ids in grouped.items():
        if len(source_ids) == 1:
            result.append(ProjectGeometryIssue(code=code, message=message, source_object_id=source_ids[0]))
        else:
            result.append(
                ProjectGeometryIssue(
                    code=code,
                    message=f'{message}. Количество объектов: {len(source_ids)}',
                )
            )
    return result


def _build_boundary(boundary: dict[str, object]) -> BaseGeometry:
    try:
        geometry = shape(boundary)
    except (TypeError, ValueError, KeyError) as exc:
        raise ProjectGeometryError('Не удалось прочитать настроенную границу проекта') from exc
    if geometry.geom_type not in {'Polygon', 'MultiPolygon'} or geometry.is_empty or not geometry.is_valid:
        raise ProjectGeometryError('Настроенная граница проекта некорректна')
    return geometry


def _build_mapping_index(layer_mappings: Iterable[dict[str, object]]) -> dict[str, ConfirmedLayerMapping]:
    mappings = {}
    for raw_mapping in layer_mappings:
        layer = raw_mapping.get('layer')
        object_type = raw_mapping.get('object_type')
        attributes = raw_mapping.get('attributes', {})
        if not isinstance(layer, str) or not layer.strip() or not isinstance(object_type, str):
            raise ProjectGeometryError('Сопоставление слоя содержит некорректный слой или тип объекта')
        if not isinstance(attributes, dict):
            raise ProjectGeometryError(f'Атрибуты сопоставления некорректны для слоя {layer}')
        try:
            geometry_role = GeometryRole(attributes.get('geometry_role', GeometryRole.LINE))
        except ValueError as exc:
            raise ProjectGeometryError(f'Для слоя {layer} указана некорректная роль геометрии') from exc
        key = layer.casefold()
        if key in mappings:
            raise ProjectGeometryError(f'Для слоя {layer} задано несколько смысловых сопоставлений')
        mappings[key] = ConfirmedLayerMapping(
            layer=layer,
            object_type=object_type,
            geometry_role=geometry_role,
            attributes=dict(attributes),
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
                message='Геометрия, подтверждённая как площадной объект, не замкнута',
                source_object_id=source_object_id,
            )
        geometry: BaseGeometry = Polygon(xy)
    else:
        geometry = LineString(xy)

    if geometry.is_empty or not geometry.is_valid:
        return None, ProjectGeometryIssue(
            code='invalid_prepared_geometry',
            message='После преобразования в локальные метры геометрия пуста или некорректна',
            source_object_id=source_object_id,
        )
    if (role is GeometryRole.AREA and geometry.area <= 0) or (role is GeometryRole.LINE and geometry.length <= 0):
        return None, ProjectGeometryIssue(
            code='degenerate_prepared_geometry',
            message='После преобразования в локальные метры геометрия имеет нулевую площадь или длину',
            source_object_id=source_object_id,
        )
    return geometry, None
