import json

from shapely import to_geojson
from shapely.geometry.base import BaseGeometry

from app.geometry import PreparedProjectGeometry, RestrictionResult
from app.schemas.preview import (
    GeoJsonGeometry,
    PlanPreviewGeometrySchema,
    PreviewIssueSchema,
    PreviewObjectSchema,
    PreviewRestrictionSchema,
    PreviewZonesSchema,
)


def build_plan_preview(
    project: PreparedProjectGeometry,
    restrictions: RestrictionResult,
) -> PlanPreviewGeometrySchema:
    """Сериализует расчётную геометрию в локальный GeoJSON-подобный payload."""

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
    issues = _deduplicate_issues((*project_issues, *restriction_issues))
    return PlanPreviewGeometrySchema(
        boundary=_geometry_payload(project.boundary),
        objects=[
            PreviewObjectSchema(
                source_object_id=obj.provenance.source_object_id,
                object_type=obj.object_type,
                geometry=_geometry_payload(obj.geometry),
            )
            for obj in project.objects
        ],
        restrictions=[
            PreviewRestrictionSchema(
                source_object_id=zone.source_object_id,
                object_type=zone.object_type,
                planting_type=zone.planting_type,
                rule_id=zone.rule_id,
                rule_version=zone.rule_version,
                min_distance_m=zone.min_distance_m,
                document=zone.document,
                clause=zone.clause,
                geometry=_geometry_payload(zone.geometry),
            )
            for zone in restrictions.zones
        ],
        zones=PreviewZonesSchema(
            tree_available=_geometry_payload(restrictions.tree_available),
            bush_available=_geometry_payload(restrictions.bush_available),
            tree_exclusion=_geometry_payload(restrictions.tree_exclusion),
            bush_exclusion=_geometry_payload(restrictions.bush_exclusion),
        ),
        issues=issues,
    )


def _geometry_payload(geometry: BaseGeometry) -> GeoJsonGeometry:
    return json.loads(to_geojson(geometry))


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
