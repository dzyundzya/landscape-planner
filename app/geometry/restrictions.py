from dataclasses import dataclass

from shapely import union_all
from shapely.geometry import GeometryCollection
from shapely.geometry.base import BaseGeometry

from app.geometry.preparation import PreparedGeometryObject, PreparedProjectGeometry
from app.models import PlantingType
from app.rules import LoadedRuleSet, NormativeRuleSchema, RuleVerificationStatus


@dataclass(frozen=True, slots=True)
class RestrictionZone:
    """Зона одного правила вокруг одного исходного объекта."""

    source_object_id: str
    object_type: str
    planting_type: PlantingType
    rule_id: str
    rule_version: str
    min_distance_m: float
    measurement_reference: str
    geometry: BaseGeometry


@dataclass(frozen=True, slots=True)
class RestrictionIssue:
    """Блокирующая неопределённость применения нормативного правила."""

    code: str
    message: str
    source_object_id: str | None = None
    planting_type: PlantingType | None = None
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class RestrictionResult:
    """Раздельные запрещённые и допустимые зоны для деревьев и кустарников."""

    zones: tuple[RestrictionZone, ...]
    tree_exclusion: BaseGeometry
    bush_exclusion: BaseGeometry
    tree_available: BaseGeometry
    bush_available: BaseGeometry
    issues: tuple[RestrictionIssue, ...]
    rules_version: str
    rules_sha256: str

    @property
    def is_verified(self) -> bool:
        """Показывает отсутствие нормативных неопределённостей."""

        return not self.issues


def build_restriction_zones(
    project: PreparedProjectGeometry,
    rule_set: LoadedRuleSet,
) -> RestrictionResult:
    """Применяет все подходящие проверенные правила к объектам проекта."""

    zones = []
    issues = [
        RestrictionIssue(
            code=issue.code,
            message=issue.message,
            source_object_id=issue.source_object_id,
        )
        for issue in project.issues
        if issue.blocking
    ]

    for obj in project.objects:
        for planting_type in PlantingType:
            object_zones, object_issues = _build_object_zones(
                obj=obj,
                planting_type=planting_type,
                rules=rule_set.data.rules,
            )
            zones.extend(object_zones)
            issues.extend(object_issues)

    tree_exclusion = _merge_zones(zones=zones, planting_type=PlantingType.TREE)
    bush_exclusion = _merge_zones(zones=zones, planting_type=PlantingType.BUSH)
    return RestrictionResult(
        zones=tuple(zones),
        tree_exclusion=tree_exclusion,
        bush_exclusion=bush_exclusion,
        tree_available=project.boundary.difference(tree_exclusion),
        bush_available=project.boundary.difference(bush_exclusion),
        issues=tuple(issues),
        rules_version=rule_set.data.version,
        rules_sha256=rule_set.sha256,
    )


def _build_object_zones(
    obj: PreparedGeometryObject,
    planting_type: PlantingType,
    rules: list[NormativeRuleSchema],
) -> tuple[list[RestrictionZone], list[RestrictionIssue]]:
    candidates = [
        rule for rule in rules if rule.object_type.value == obj.object_type and rule.vegetation_type is planting_type
    ]
    if not candidates:
        return [], [
            RestrictionIssue(
                code='missing_rule',
                message='Для класса объекта отсутствует нормативное правило',
                source_object_id=obj.provenance.source_object_id,
                planting_type=planting_type,
            )
        ]

    zones = []
    issues = []
    applicable_rule_found = False
    for rule in candidates:
        missing = sorted({*rule.required_attributes, *rule.conditions, 'measurement_reference'} - obj.attributes.keys())
        if missing:
            issues.append(
                RestrictionIssue(
                    code='missing_rule_attributes',
                    message=f'Для применения правила отсутствуют атрибуты: {", ".join(missing)}',
                    source_object_id=obj.provenance.source_object_id,
                    planting_type=planting_type,
                    rule_id=rule.id,
                )
            )
            continue
        if any(obj.attributes[key] != value for key, value in rule.conditions.items()):
            continue
        if obj.attributes['measurement_reference'] != rule.measurement_reference:
            issues.append(
                RestrictionIssue(
                    code='measurement_reference_mismatch',
                    message='Способ измерения исходной геометрии не соответствует нормативному правилу',
                    source_object_id=obj.provenance.source_object_id,
                    planting_type=planting_type,
                    rule_id=rule.id,
                )
            )
            continue

        applicable_rule_found = True
        if rule.verification_status is not RuleVerificationStatus.VERIFIED:
            issues.append(
                RestrictionIssue(
                    code='unverified_rule',
                    message='Применимое нормативное правило ещё не проверено по первоисточнику',
                    source_object_id=obj.provenance.source_object_id,
                    planting_type=planting_type,
                    rule_id=rule.id,
                )
            )
            continue
        zones.append(
            RestrictionZone(
                source_object_id=obj.provenance.source_object_id,
                object_type=obj.object_type,
                planting_type=planting_type,
                rule_id=rule.id,
                rule_version=rule.version,
                min_distance_m=rule.min_distance_m,
                measurement_reference=rule.measurement_reference,
                geometry=obj.geometry.buffer(rule.min_distance_m),
            )
        )

    if not applicable_rule_found and not issues:
        issues.append(
            RestrictionIssue(
                code='no_applicable_rule',
                message='Ни одно правило не соответствует подтверждённым атрибутам объекта',
                source_object_id=obj.provenance.source_object_id,
                planting_type=planting_type,
            )
        )
    return zones, issues


def _merge_zones(zones: list[RestrictionZone], planting_type: PlantingType) -> BaseGeometry:
    geometries = [zone.geometry for zone in zones if zone.planting_type is planting_type]
    if not geometries:
        return GeometryCollection()
    return union_all(geometries)
