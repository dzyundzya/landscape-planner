import pytest
from pydantic import ValidationError

from app.schemas.config_snapshot import ConfigSnapshotUpsertSchema, MultiPolygonBoundarySchema


def valid_config_data() -> dict[str, object]:
    """Возвращает минимальный набор настроек для проверки схемы."""

    return {
        'coordinate_unit': 'meter',
        'boundary': {
            'type': 'Polygon',
            'coordinates': [[[0, 0], [1, 0], [0, 1], [0, 0]]],
        },
        'layer_mappings': [],
        'generation': {
            'max_trees': 0,
            'max_bushes': 0,
            'tree_tree_distance_m': 1,
            'bush_bush_distance_m': 1,
            'tree_bush_distance_m': 1,
            'grid_spacing_m': 1,
        },
    }


def test_config_rejects_duplicate_layer_mappings() -> None:
    """Проверяет запрет повторной классификации слоя без учёта регистра."""

    data = valid_config_data()
    data['layer_mappings'] = [
        {'layer': 'Trees', 'object_type': 'existing_tree'},
        {'layer': 'trees', 'object_type': 'ignore'},
    ]

    with pytest.raises(ValidationError):
        ConfigSnapshotUpsertSchema.model_validate(data)


def test_config_rejects_non_finite_generation_value() -> None:
    """Проверяет отклонение бесконечного межпосадочного расстояния."""

    data = valid_config_data()
    data['generation']['tree_tree_distance_m'] = float('inf')  # type: ignore[index]

    with pytest.raises(ValidationError):
        ConfigSnapshotUpsertSchema.model_validate(data)


def test_multi_polygon_boundary_is_supported() -> None:
    """Проверяет поддержку границы участка из нескольких полигонов."""

    boundary = MultiPolygonBoundarySchema(
        type='MultiPolygon',
        coordinates=[
            [[[0, 0], [2, 0], [0, 2], [0, 0]]],
            [[[5, 5], [6, 5], [5, 6], [5, 5]]],
        ],
    )

    assert len(boundary.coordinates) == 2
