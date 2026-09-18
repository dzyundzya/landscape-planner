import math
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import Point

from app.geometry import RestrictionResult
from app.models import PlantingType
from app.schemas.config_snapshot import GenerationParametersSchema

GENERATOR_VERSION = 'hex-grid-greedy/1'
MAX_CANDIDATE_COUNT = 250_000
COORDINATE_PRECISION = 6
DISTANCE_EPSILON_M = 1e-9
HEX_OFFSETS = (
    (0.0, 0.0),
    (0.5, 0.0),
    (0.0, 0.5),
    (0.5, 0.5),
    (0.25, 0.25),
    (0.75, 0.25),
    (0.25, 0.75),
)


class PlantingGenerationError(Exception):
    """Генерация невозможна при текущей геометрии или параметрах."""


@dataclass(frozen=True, slots=True)
class GeneratedPlanting:
    """Детерминированно выбранная позиция посадки."""

    type: PlantingType
    x_m: float
    y_m: float


@dataclass(frozen=True, slots=True)
class PlantingGenerationResult:
    """Результат лучшего сценария фиксированной гексагональной сетки."""

    generator_version: str
    plantings: tuple[GeneratedPlanting, ...]
    candidate_count: int
    rejected_candidate_count: int
    selected_offset_index: int
    offset_x_m: float
    offset_y_m: float
    grid_spacing_m: float
    warnings: tuple[str, ...]

    @property
    def tree_count(self) -> int:
        return sum(planting.type is PlantingType.TREE for planting in self.plantings)

    @property
    def bush_count(self) -> int:
        return sum(planting.type is PlantingType.BUSH for planting in self.plantings)


class _PointIndex:
    """Пространственная сетка для проверки интервалов между посадками."""

    def __init__(self, cell_size: float) -> None:
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)

    def add(self, x: float, y: float) -> None:
        self.cells[self._cell(x=x, y=y)].append((x, y))

    def allows(self, x: float, y: float, min_distance: float) -> bool:
        radius = max(1, math.ceil(min_distance / self.cell_size))
        cell_x, cell_y = self._cell(x=x, y=y)
        for delta_x in range(-radius, radius + 1):
            for delta_y in range(-radius, radius + 1):
                for other_x, other_y in self.cells.get((cell_x + delta_x, cell_y + delta_y), ()):
                    if math.hypot(x - other_x, y - other_y) + DISTANCE_EPSILON_M < min_distance:
                        return False
        return True

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.cell_size), math.floor(y / self.cell_size)


def generate_plantings(
    restrictions: RestrictionResult,
    parameters: GenerationParametersSchema,
) -> PlantingGenerationResult:
    """Выбирает лучший из фиксированных сценариев гексагональной сетки."""

    if restrictions.issues:
        raise PlantingGenerationError('Генерация заблокирована неразрешёнными ограничениями проекта')

    combined_available = restrictions.tree_available.union(restrictions.bush_available)
    if combined_available.is_empty:
        return _empty_result(parameters=parameters, warning='На участке отсутствует доступная для посадок область')

    row_spacing = parameters.grid_spacing_m * math.sqrt(3) / 2
    scenarios = []
    for offset_index, (offset_x_factor, offset_y_factor) in enumerate(HEX_OFFSETS):
        offset_x = offset_x_factor * parameters.grid_spacing_m
        offset_y = offset_y_factor * row_spacing
        candidates = _build_candidates(
            available=combined_available,
            spacing=parameters.grid_spacing_m,
            row_spacing=row_spacing,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        plantings = _select_plantings(
            candidates=candidates,
            restrictions=restrictions,
            parameters=parameters,
        )
        scenarios.append(
            PlantingGenerationResult(
                generator_version=GENERATOR_VERSION,
                plantings=plantings,
                candidate_count=len(candidates),
                rejected_candidate_count=len(candidates) - len(plantings),
                selected_offset_index=offset_index,
                offset_x_m=offset_x,
                offset_y_m=offset_y,
                grid_spacing_m=parameters.grid_spacing_m,
                warnings=_build_warnings(plantings=plantings, parameters=parameters),
            )
        )

    return max(
        scenarios,
        key=lambda result: (result.tree_count, result.bush_count, -result.selected_offset_index),
    )


def _build_candidates(
    available,
    spacing: float,
    row_spacing: float,
    offset_x: float,
    offset_y: float,
) -> tuple[tuple[float, float], ...]:
    min_x, min_y, max_x, max_y = available.bounds
    first_row = math.floor((min_y - offset_y) / row_spacing) - 1
    last_row = math.ceil((max_y - offset_y) / row_spacing) + 1
    first_column = math.floor((min_x - offset_x) / spacing) - 2
    last_column = math.ceil((max_x - offset_x) / spacing) + 2
    estimated_count = (last_row - first_row + 1) * (last_column - first_column + 1)
    if estimated_count > MAX_CANDIDATE_COUNT:
        raise PlantingGenerationError(f'Гексагональная сетка содержит более {MAX_CANDIDATE_COUNT} потенциальных точек')

    candidates = set()
    for row in range(first_row, last_row + 1):
        y = offset_y + row * row_spacing
        row_shift = spacing / 2 if row % 2 else 0.0
        for column in range(first_column, last_column + 1):
            x = offset_x + column * spacing + row_shift
            rounded = (round(x, COORDINATE_PRECISION), round(y, COORDINATE_PRECISION))
            if available.contains(Point(*rounded)):
                candidates.add(rounded)
    return tuple(sorted(candidates, key=lambda point: (point[1], point[0])))


def _select_plantings(
    candidates: tuple[tuple[float, float], ...],
    restrictions: RestrictionResult,
    parameters: GenerationParametersSchema,
) -> tuple[GeneratedPlanting, ...]:
    tree_index = _PointIndex(cell_size=max(parameters.tree_tree_distance_m, parameters.tree_bush_distance_m))
    trees = []
    for x, y in candidates:
        if len(trees) >= parameters.max_trees:
            break
        if restrictions.tree_available.contains(Point(x, y)) and tree_index.allows(
            x=x,
            y=y,
            min_distance=parameters.tree_tree_distance_m,
        ):
            trees.append(GeneratedPlanting(type=PlantingType.TREE, x_m=x, y_m=y))
            tree_index.add(x=x, y=y)

    bush_index = _PointIndex(cell_size=parameters.bush_bush_distance_m)
    bushes = []
    for x, y in candidates:
        if len(bushes) >= parameters.max_bushes:
            break
        if not restrictions.bush_available.contains(Point(x, y)):
            continue
        if not tree_index.allows(x=x, y=y, min_distance=parameters.tree_bush_distance_m):
            continue
        if not bush_index.allows(x=x, y=y, min_distance=parameters.bush_bush_distance_m):
            continue
        bushes.append(GeneratedPlanting(type=PlantingType.BUSH, x_m=x, y_m=y))
        bush_index.add(x=x, y=y)
    return (*trees, *bushes)


def _build_warnings(
    plantings: tuple[GeneratedPlanting, ...],
    parameters: GenerationParametersSchema,
) -> tuple[str, ...]:
    tree_count = sum(planting.type is PlantingType.TREE for planting in plantings)
    bush_count = sum(planting.type is PlantingType.BUSH for planting in plantings)
    warnings = []
    if tree_count < parameters.max_trees:
        warnings.append('В доступной области не удалось разместить заданное максимальное количество деревьев')
    if bush_count < parameters.max_bushes:
        warnings.append('В доступной области не удалось разместить заданное максимальное количество кустарников')
    return tuple(warnings)


def _empty_result(parameters: GenerationParametersSchema, warning: str) -> PlantingGenerationResult:
    return PlantingGenerationResult(
        generator_version=GENERATOR_VERSION,
        plantings=(),
        candidate_count=0,
        rejected_candidate_count=0,
        selected_offset_index=0,
        offset_x_m=0.0,
        offset_y_m=0.0,
        grid_spacing_m=parameters.grid_spacing_m,
        warnings=(warning,),
    )
