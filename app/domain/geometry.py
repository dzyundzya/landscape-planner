from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class Point2D:
    """Точка в координатах исходного чертежа."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class CoordinateTransform:
    """Обратимое преобразование координат DXF в локальные метры."""

    scale_to_meters: float
    source_origin: Point2D = Point2D(0.0, 0.0)
    local_origin_m: Point2D = Point2D(0.0, 0.0)

    def __post_init__(self) -> None:
        values = (
            self.scale_to_meters,
            self.source_origin.x,
            self.source_origin.y,
            self.local_origin_m.x,
            self.local_origin_m.y,
        )
        if not all(isfinite(value) for value in values) or self.scale_to_meters <= 0:
            raise ValueError('Преобразование координат должно содержать конечные значения и положительный масштаб')

    def to_local_meters(self, point: Point2D) -> Point2D:
        """Переводит точку исходного DXF в локальные метры."""

        return Point2D(
            x=(point.x - self.source_origin.x) * self.scale_to_meters + self.local_origin_m.x,
            y=(point.y - self.source_origin.y) * self.scale_to_meters + self.local_origin_m.y,
        )

    def to_source(self, point: Point2D) -> Point2D:
        """Возвращает локальную точку в координаты исходного DXF."""

        return Point2D(
            x=(point.x - self.local_origin_m.x) / self.scale_to_meters + self.source_origin.x,
            y=(point.y - self.local_origin_m.y) / self.scale_to_meters + self.source_origin.y,
        )


@dataclass(frozen=True, slots=True)
class GeometryProvenance:
    """Происхождение нормализованного объекта DXF."""

    source_object_id: str
    handle: str | None
    entity_type: str
    layer: str
    source_layer: str
    insert_path: tuple[str, ...]
    min_z: float
    max_z: float


@dataclass(frozen=True, slots=True)
class NormalizedPolyline:
    """Линейная 2D-геометрия с явно сохранённой замкнутостью."""

    points: tuple[Point2D, ...]
    closed: bool
    provenance: GeometryProvenance


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    """Причина пропуска или неполной нормализации объекта."""

    code: str
    message: str
    source_object_id: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Нормализованные объекты и диагностические проблемы."""

    geometries: tuple[NormalizedPolyline, ...]
    issues: tuple[NormalizationIssue, ...]
    truncated_layers: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class NormalizationOptions:
    """Явные параметры точности и защиты рекурсивного раскрытия."""

    curve_tolerance: float
    max_insert_depth: int = 16
    max_geometries_per_layer: int | None = None
    max_points_per_geometry: int | None = None
    collect_issues: bool = True

    def __post_init__(self) -> None:
        if not isfinite(self.curve_tolerance) or self.curve_tolerance <= 0:
            raise ValueError('Погрешность аппроксимации кривых должна быть положительной')
        if not 1 <= self.max_insert_depth <= 64:
            raise ValueError('Максимальная глубина INSERT должна быть от 1 до 64')
        if self.max_geometries_per_layer is not None and self.max_geometries_per_layer < 1:
            raise ValueError('Лимит геометрий слоя должен быть положительным')
        if self.max_points_per_geometry is not None and self.max_points_per_geometry < 2:
            raise ValueError('Лимит точек геометрии должен быть не меньше двух')
