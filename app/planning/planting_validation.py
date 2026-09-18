from dataclasses import dataclass
from math import hypot

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from app.models import PlantingType
from app.schemas.config_snapshot import GenerationParametersSchema


class PlantingValidationError(Exception):
    """Посадка нарушает границу или проектные интервалы."""


@dataclass(frozen=True, slots=True)
class PlantingCandidate:
    """Независимое от ORM представление посадки для проверки."""

    type: PlantingType
    x_m: float
    y_m: float


def build_boundary(boundary: dict[str, object]) -> BaseGeometry:
    """Строит и проверяет геометрию подтверждённой границы."""

    geometry = shape(boundary)
    if geometry.geom_type not in {'Polygon', 'MultiPolygon'} or geometry.is_empty or not geometry.is_valid:
        raise PlantingValidationError('Настроенная граница проекта некорректна')
    return geometry


def validate_planting_set(
    candidates: list[PlantingCandidate],
    boundary: dict[str, object],
    generation: dict[str, object],
) -> None:
    """Проверяет набор посадок по границе, лимитам и межпосадочным интервалам."""

    geometry = build_boundary(boundary=boundary)
    parameters = GenerationParametersSchema.model_validate(generation)

    tree_count = sum(candidate.type is PlantingType.TREE for candidate in candidates)
    bush_count = sum(candidate.type is PlantingType.BUSH for candidate in candidates)
    if tree_count > parameters.max_trees:
        raise PlantingValidationError('Количество деревьев превышает лимит конфигурации')
    if bush_count > parameters.max_bushes:
        raise PlantingValidationError('Количество кустарников превышает лимит конфигурации')

    for index, candidate in enumerate(candidates):
        if not geometry.contains(Point(candidate.x_m, candidate.y_m)):
            raise PlantingValidationError(f'Посадка с индексом {index} находится вне границы проекта')

        for other_index in range(index):
            other = candidates[other_index]
            distance = hypot(candidate.x_m - other.x_m, candidate.y_m - other.y_m)
            required = _get_required_distance(
                first_type=candidate.type,
                second_type=other.type,
                parameters=parameters,
            )
            if distance + 1e-9 < required:
                raise PlantingValidationError(
                    f'Для посадок с индексами {other_index} и {index} требуется расстояние {required} м, фактическое — {distance} м'
                )


def _get_required_distance(
    first_type: PlantingType,
    second_type: PlantingType,
    parameters: GenerationParametersSchema,
) -> float:
    if first_type is PlantingType.TREE and second_type is PlantingType.TREE:
        return parameters.tree_tree_distance_m
    if first_type is PlantingType.BUSH and second_type is PlantingType.BUSH:
        return parameters.bush_bush_distance_m
    return parameters.tree_bush_distance_m
