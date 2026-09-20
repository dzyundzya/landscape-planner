import json
from dataclasses import dataclass

from shapely import get_num_coordinates, to_geojson
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from app.geometry import PreparedProjectGeometry, RestrictionResult
from app.schemas.preview import (
    GeoJsonGeometry,
    PlanPreviewGeometrySchema,
    PreviewIssueSchema,
    PreviewObjectSchema,
    PreviewRestrictionSchema,
    PreviewSummarySchema,
    PreviewZonesSchema,
)

DEFAULT_SIMPLIFY_TOLERANCE_M = 0.1
DEFAULT_MAX_OBJECTS = 2_000
DEFAULT_MAX_RESTRICTIONS = 2_000
DEFAULT_MAX_COORDINATES = 200_000


@dataclass(slots=True)
class _PreviewGeometrySerializer:
    """Сериализует геометрию в пределах заранее выделенного бюджета координат."""

    tolerance_m: float
    displayed_coordinate_count: int = 0
    simplified: bool = False

    def payload(self, geometry: BaseGeometry, coordinate_budget: int) -> GeoJsonGeometry:
        original_count = int(get_num_coordinates(geometry))
        rendered = geometry
        tolerance = self.tolerance_m
        while int(get_num_coordinates(rendered)) > coordinate_budget and tolerance <= self.tolerance_m * 4_096:
            rendered = geometry.simplify(tolerance, preserve_topology=True)
            tolerance *= 2

        if int(get_num_coordinates(rendered)) > coordinate_budget:
            rendered = _fallback_geometry(geometry)

        rendered_count = int(get_num_coordinates(rendered))
        self.displayed_coordinate_count += rendered_count
        self.simplified = self.simplified or rendered_count < original_count
        return json.loads(to_geojson(rendered))


def build_plan_preview(
    project: PreparedProjectGeometry,
    restrictions: RestrictionResult,
    simplify_tolerance_m: float = DEFAULT_SIMPLIFY_TOLERANCE_M,
    max_objects: int = DEFAULT_MAX_OBJECTS,
    max_restrictions: int = DEFAULT_MAX_RESTRICTIONS,
    max_coordinates: int = DEFAULT_MAX_COORDINATES,
) -> PlanPreviewGeometrySchema:
    """Сериализует облегчённую расчётную геометрию для браузера."""

    if simplify_tolerance_m <= 0 or max_objects < 1 or max_restrictions < 1 or max_coordinates < 100:
        raise ValueError('Параметры ограничения preview должны быть положительными')

    visible_objects = project.objects[:max_objects]
    visible_restrictions = restrictions.zones[:max_restrictions]
    serializer = _PreviewGeometrySerializer(tolerance_m=simplify_tolerance_m)
    boundary_budget = max(8, max_coordinates // 10)
    zone_budget = max(8, max_coordinates // 8)
    object_budget = max(8, (max_coordinates // 5) // max(1, len(visible_objects)))
    restriction_budget = max(8, (max_coordinates // 5) // max(1, len(visible_restrictions)))
    source_coordinate_count = _source_coordinate_count(project=project, restrictions=restrictions)

    project_issues = [
        PreviewIssueSchema(
            code=issue.code,
            message=issue.message,
            source_object_id=issue.source_object_id,
        )
        for issue in project.issues
    ]
    restriction_issues = [
        PreviewIssueSchema(
            code=issue.code,
            message=issue.message,
            source_object_id=issue.source_object_id,
            planting_type=issue.planting_type,
            rule_id=issue.rule_id,
        )
        for issue in restrictions.issues
    ]
    preview_issues = []
    if len(visible_objects) < len(project.objects):
        preview_issues.append(
            PreviewIssueSchema(
                code='preview_objects_omitted',
                message=f'Для быстрого просмотра показано {len(visible_objects)} из {len(project.objects)} объектов',
            )
        )
    if len(visible_restrictions) < len(restrictions.zones):
        preview_issues.append(
            PreviewIssueSchema(
                code='preview_restrictions_omitted',
                message=(
                    f'Для быстрого просмотра показано {len(visible_restrictions)} '
                    f'из {len(restrictions.zones)} нормативных зон'
                ),
            )
        )
    boundary = serializer.payload(project.boundary, boundary_budget)
    objects = [
        PreviewObjectSchema(
            source_object_id=obj.provenance.source_object_id,
            object_type=obj.object_type,
            geometry=serializer.payload(obj.geometry, object_budget),
        )
        for obj in visible_objects
    ]
    preview_restrictions = [
        PreviewRestrictionSchema(
            source_object_id=zone.source_object_id,
            object_type=zone.object_type,
            planting_type=zone.planting_type,
            rule_id=zone.rule_id,
            rule_version=zone.rule_version,
            min_distance_m=zone.min_distance_m,
            document=zone.document,
            clause=zone.clause,
            geometry=serializer.payload(zone.geometry, restriction_budget),
        )
        for zone in visible_restrictions
    ]
    zones = PreviewZonesSchema(
        tree_available=serializer.payload(restrictions.tree_available, zone_budget),
        bush_available=serializer.payload(restrictions.bush_available, zone_budget),
        tree_exclusion=serializer.payload(restrictions.tree_exclusion, zone_budget),
        bush_exclusion=serializer.payload(restrictions.bush_exclusion, zone_budget),
    )
    if serializer.simplified:
        preview_issues.append(
            PreviewIssueSchema(
                code='preview_geometry_simplified',
                message='Геометрия упрощена только для быстрого просмотра; расчёт выполнен по исходной точности',
            )
        )
    issues = _deduplicate_issues((*project_issues, *restriction_issues, *preview_issues))
    return PlanPreviewGeometrySchema(
        boundary=boundary,
        objects=objects,
        restrictions=preview_restrictions,
        zones=zones,
        issues=issues,
        summary=PreviewSummarySchema(
            object_count=len(project.objects),
            displayed_object_count=len(visible_objects),
            restriction_count=len(restrictions.zones),
            displayed_restriction_count=len(visible_restrictions),
            source_coordinate_count=source_coordinate_count,
            displayed_coordinate_count=serializer.displayed_coordinate_count,
            simplified=serializer.simplified,
        ),
    )


def _source_coordinate_count(project: PreparedProjectGeometry, restrictions: RestrictionResult) -> int:
    geometries = (
        project.boundary,
        *(obj.geometry for obj in project.objects),
        *(zone.geometry for zone in restrictions.zones),
        restrictions.tree_available,
        restrictions.bush_available,
        restrictions.tree_exclusion,
        restrictions.bush_exclusion,
    )
    return sum(int(get_num_coordinates(geometry)) for geometry in geometries)


def _fallback_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.geom_type in {'LineString', 'LinearRing'}:
        coordinates = list(geometry.coords)
        return LineString((coordinates[0], coordinates[-1]))
    return geometry.envelope


def _deduplicate_issues(issues: tuple[PreviewIssueSchema, ...]) -> list[PreviewIssueSchema]:
    unique_issues: dict[tuple[object, ...], PreviewIssueSchema] = {}
    for issue in issues:
        key = (
            issue.code,
            issue.message,
            issue.source_object_id,
            issue.planting_type,
            issue.rule_id,
        )
        unique_issues.setdefault(key, issue)
    return list(unique_issues.values())
