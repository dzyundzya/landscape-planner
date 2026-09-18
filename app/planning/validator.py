import math
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from shapely import STRtree
from shapely.geometry import Point

from app.geometry import PreparedProjectGeometry, RestrictionIssue, RestrictionResult, RestrictionZone
from app.models import PlantingType, ValidationStatus
from app.schemas.config_snapshot import GenerationParametersSchema
from app.schemas.plan_validation import CheckResultSchema, PlanValidationPublishSchema

VALIDATOR_VERSION = 'geometry-validator/1'
DISTANCE_EPSILON_M = 1e-9


@dataclass(frozen=True, slots=True)
class ValidationPlanting:
    """Посадка с устойчивым ID для независимой проверки."""

    public_id: UUID
    type: PlantingType
    x_m: float
    y_m: float


def validate_plan_geometry(
    project: PreparedProjectGeometry,
    restrictions: RestrictionResult,
    plantings: list[ValidationPlanting],
    parameters: GenerationParametersSchema,
) -> PlanValidationPublishSchema:
    """Независимо проверяет границу, нормы и интервалы всех посадок."""

    checks = []
    checks.extend(_build_input_issue_checks(issues=restrictions.issues, plantings=plantings))
    checks.extend(_build_boundary_checks(boundary=project.boundary, plantings=plantings))
    checks.extend(_build_normative_checks(zones=restrictions.zones, plantings=plantings))
    checks.extend(_build_spacing_checks(plantings=plantings, parameters=parameters))
    if not plantings:
        checks.append(
            CheckResultSchema(
                check_type='empty_plan',
                status=ValidationStatus.PASSED,
                reason='Пустой план допустим и не содержит нарушающих посадок',
            )
        )
    return PlanValidationPublishSchema(validator_version=VALIDATOR_VERSION, checks=checks)


def _build_input_issue_checks(
    issues: tuple[RestrictionIssue, ...],
    plantings: list[ValidationPlanting],
) -> list[CheckResultSchema]:
    checks = []
    for issue in issues:
        matching = [
            planting for planting in plantings if issue.planting_type is None or planting.type is issue.planting_type
        ]
        if not matching:
            checks.append(_issue_check(issue=issue, planting_id=None))
            continue
        checks.extend(_issue_check(issue=issue, planting_id=planting.public_id) for planting in matching)
    return checks


def _issue_check(issue: RestrictionIssue, planting_id: UUID | None) -> CheckResultSchema:
    return CheckResultSchema(
        check_type=issue.code,
        status=ValidationStatus.NEEDS_VERIFICATION,
        planting_id=planting_id,
        rule_id=issue.rule_id,
        source_object_id=issue.source_object_id,
        reason=issue.message,
    )


def _build_boundary_checks(boundary, plantings: list[ValidationPlanting]) -> list[CheckResultSchema]:
    checks = []
    for planting in plantings:
        inside = boundary.contains(Point(planting.x_m, planting.y_m))
        checks.append(
            CheckResultSchema(
                check_type='project_boundary',
                status=ValidationStatus.PASSED if inside else ValidationStatus.FAILED,
                planting_id=planting.public_id,
                reason=(
                    'Посадка находится строго внутри подтверждённой границы проекта'
                    if inside
                    else 'Посадка находится вне границы проекта или на её границе'
                ),
            )
        )
    return checks


def _build_normative_checks(
    zones: tuple[RestrictionZone, ...],
    plantings: list[ValidationPlanting],
) -> list[CheckResultSchema]:
    zones_by_type = {
        planting_type: tuple(zone for zone in zones if zone.planting_type is planting_type)
        for planting_type in PlantingType
    }
    trees = {
        planting_type: STRtree([zone.geometry for zone in typed_zones]) if typed_zones else None
        for planting_type, typed_zones in zones_by_type.items()
    }
    checks = []
    for planting in plantings:
        point = Point(planting.x_m, planting.y_m)
        typed_zones = zones_by_type[planting.type]
        tree = trees[planting.type]
        violations = []
        if tree is not None:
            for raw_index in tree.query(point):
                zone = typed_zones[int(raw_index)]
                actual = point.distance(zone.source_geometry)
                if actual + DISTANCE_EPSILON_M < zone.min_distance_m:
                    violations.append(_normative_failure(planting=planting, zone=zone, actual=actual))
        if violations:
            checks.extend(violations)
        else:
            checks.append(
                CheckResultSchema(
                    check_type='normative_distances',
                    status=ValidationStatus.PASSED,
                    planting_id=planting.public_id,
                    reason='Посадка не нарушает ни одну применимую нормативную зону',
                )
            )
    return checks


def _normative_failure(
    planting: ValidationPlanting,
    zone: RestrictionZone,
    actual: float,
) -> CheckResultSchema:
    return CheckResultSchema(
        check_type='normative_distance',
        status=ValidationStatus.FAILED,
        planting_id=planting.public_id,
        actual=_decimal_distance(actual),
        required=_decimal_distance(zone.min_distance_m),
        unit='m',
        rule_id=zone.rule_id,
        rule_version=zone.rule_version,
        source_object_id=zone.source_object_id,
        document=zone.document,
        clause=zone.clause,
        reason=f'Расстояние от посадки до объекта меньше требуемого отступа от {zone.measurement_reference}',
    )


def _build_spacing_checks(
    plantings: list[ValidationPlanting],
    parameters: GenerationParametersSchema,
) -> list[CheckResultSchema]:
    if not plantings:
        return []
    max_distance = max(
        parameters.tree_tree_distance_m,
        parameters.bush_bush_distance_m,
        parameters.tree_bush_distance_m,
    )
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    worst_violations: dict[int, tuple[float, float, int]] = {}
    for index, planting in enumerate(plantings):
        cell_x = math.floor(planting.x_m / max_distance)
        cell_y = math.floor(planting.y_m / max_distance)
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                for other_index in cells.get((cell_x + delta_x, cell_y + delta_y), ()):
                    other = plantings[other_index]
                    actual = math.hypot(planting.x_m - other.x_m, planting.y_m - other.y_m)
                    required = _required_spacing(first=planting.type, second=other.type, parameters=parameters)
                    if actual + DISTANCE_EPSILON_M < required:
                        _remember_worst(worst_violations, index, actual, required, other_index)
                        _remember_worst(worst_violations, other_index, actual, required, index)
        cells[(cell_x, cell_y)].append(index)

    checks = []
    for index, planting in enumerate(plantings):
        violation = worst_violations.get(index)
        if violation is None:
            checks.append(
                CheckResultSchema(
                    check_type='planting_spacing',
                    status=ValidationStatus.PASSED,
                    planting_id=planting.public_id,
                    reason='Межпосадочные интервалы соблюдены',
                )
            )
            continue
        actual, required, other_index = violation
        checks.append(
            CheckResultSchema(
                check_type='planting_spacing',
                status=ValidationStatus.FAILED,
                planting_id=planting.public_id,
                actual=_decimal_distance(actual),
                required=_decimal_distance(required),
                unit='m',
                source_object_id=f'planting:{plantings[other_index].public_id}',
                reason='Расстояние до другой посадки меньше проектного интервала',
            )
        )
    return checks


def _remember_worst(
    violations: dict[int, tuple[float, float, int]],
    index: int,
    actual: float,
    required: float,
    other_index: int,
) -> None:
    current = violations.get(index)
    if current is None or required - actual > current[1] - current[0]:
        violations[index] = (actual, required, other_index)


def _required_spacing(
    first: PlantingType,
    second: PlantingType,
    parameters: GenerationParametersSchema,
) -> float:
    if first is PlantingType.TREE and second is PlantingType.TREE:
        return parameters.tree_tree_distance_m
    if first is PlantingType.BUSH and second is PlantingType.BUSH:
        return parameters.bush_bush_distance_m
    return parameters.tree_bush_distance_m


def _decimal_distance(value: float) -> Decimal:
    return Decimal(str(round(value, 9)))
