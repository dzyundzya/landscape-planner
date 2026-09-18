from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class Point2D:
    """Точка в координатах исходного чертежа."""

    x: float
    y: float


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


@dataclass(frozen=True, slots=True)
class NormalizationOptions:
    """Явные параметры точности и защиты рекурсивного раскрытия."""

    curve_tolerance: float
    max_insert_depth: int = 16

    def __post_init__(self) -> None:
        if not isfinite(self.curve_tolerance) or self.curve_tolerance <= 0:
            raise ValueError('Curve tolerance must be positive')
        if not 1 <= self.max_insert_depth <= 64:
            raise ValueError('Max insert depth must be between 1 and 64')
