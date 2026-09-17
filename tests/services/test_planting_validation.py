import pytest

from app.models import PlantingType
from app.planning import (
    PlantingCandidate,
    PlantingValidationError,
    validate_planting_set,
)

BOUNDARY = {
    'type': 'Polygon',
    'coordinates': [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
}
GENERATION = {
    'max_trees': 2,
    'max_bushes': 2,
    'tree_tree_distance_m': 5,
    'bush_bush_distance_m': 1.5,
    'tree_bush_distance_m': 2,
    'grid_spacing_m': 1,
}


def test_validate_planting_set_accepts_exact_required_distance() -> None:
    """Проверяет допустимость посадок ровно на минимальном интервале."""

    validate_planting_set(
        candidates=[
            PlantingCandidate(type=PlantingType.TREE, x_m=1, y_m=1),
            PlantingCandidate(type=PlantingType.TREE, x_m=4, y_m=5),
        ],
        boundary=BOUNDARY,
        generation=GENERATION,
    )


def test_validate_planting_set_rejects_boundary_point() -> None:
    """Проверяет отклонение посадки непосредственно на границе участка."""

    with pytest.raises(PlantingValidationError, match='outside the project boundary'):
        validate_planting_set(
            candidates=[PlantingCandidate(type=PlantingType.BUSH, x_m=0, y_m=1)],
            boundary=BOUNDARY,
            generation=GENERATION,
        )


def test_validate_planting_set_rejects_invalid_boundary() -> None:
    """Проверяет отклонение самопересекающейся границы участка."""

    with pytest.raises(PlantingValidationError, match='boundary is invalid'):
        validate_planting_set(
            candidates=[],
            boundary={
                'type': 'Polygon',
                'coordinates': [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
            },
            generation=GENERATION,
        )
