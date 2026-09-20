from collections import Counter, defaultdict
from heapq import heappush, heapreplace
from itertools import islice
from pathlib import Path

import ezdxf
from ezdxf import bbox, units
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.lldxf.const import DXFError
from ezdxf.path import make_path
from shapely.geometry import Polygon

from app.cad.layer_suggestions import suggest_layer
from app.models import AnalysisWarningSeverity
from app.schemas.analysis import (
    AnalysisBoundaryCandidateSchema,
    AnalysisBoundsSchema,
    AnalysisLayerSchema,
    AnalysisLayerSuggestionSchema,
    AnalysisResultSchema,
    AnalysisWarningSchema,
)

SUPPORTED_ENTITY_TYPES = frozenset(
    {
        'ARC',
        'ATTDEF',
        'ATTRIB',
        'CIRCLE',
        'INSERT',
        'LINE',
        'LWPOLYLINE',
        'MTEXT',
        'POLYLINE',
        'TEXT',
    }
)
LABEL_ENTITY_TYPES = frozenset({'ATTDEF', 'ATTRIB', 'MTEXT', 'TEXT'})
BOUNDARY_CANDIDATE_LIMIT = 40
BOUNDARY_COORDINATE_LIMIT = 512
UNIT_SCALE_TO_METERS = {
    1: 0.0254,
    2: 0.3048,
    4: 0.001,
    5: 0.01,
    6: 1.0,
    7: 1000.0,
    10: 0.9144,
}


class DxfAnalysisError(Exception):
    """DXF не удалось безопасно прочитать или проанализировать."""


def analyze_dxf(path: Path) -> AnalysisResultSchema:
    """Строит детерминированную диагностическую сводку DXF без бизнес-классификации."""

    try:
        document = ezdxf.readfile(path)
    except (DXFError, OSError, UnicodeError) as exc:
        raise DxfAnalysisError('Не удалось прочитать исходный DXF') from exc

    block_layouts = [block for block in document.blocks if not block.is_any_layout]
    entity_counts: Counter[str] = Counter()
    layer_counts: dict[str, Counter[str]] = defaultdict(Counter)
    block_layer_counts: dict[str, Counter[str]] = defaultdict(Counter)
    unsupported_counts: Counter[str] = Counter()
    block_references: Counter[str] = Counter()
    labels_count = 0

    for layout in document.layouts:
        for entity in layout:
            entity_type = entity.dxftype()
            entity_counts[entity_type] += 1
            layer_counts[entity.dxf.get('layer', '0')][entity_type] += 1
            labels_count += _collect_common_entity_stats(
                entity=entity,
                unsupported_counts=unsupported_counts,
                block_references=block_references,
            )
    for block in block_layouts:
        for entity in block:
            block_layer_counts[entity.dxf.get('layer', '0')][entity.dxftype()] += 1
            labels_count += _collect_common_entity_stats(
                entity=entity,
                unsupported_counts=unsupported_counts,
                block_references=block_references,
            )

    sorted_entity_counts = dict(sorted(entity_counts.items()))
    unsupported_entities = dict(sorted(unsupported_counts.items()))
    external_references = _get_external_references(block_layouts)
    bounds, bounds_failed = _get_modelspace_bounds(document)
    warnings = _build_warnings(
        document=document,
        entity_counts=sorted_entity_counts,
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds_failed=bounds_failed,
    )

    return AnalysisResultSchema(
        dxf_version=document.dxfversion,
        drawing_units=units.decode(document.units),
        entity_counts=sorted_entity_counts,
        layers=_get_layers(
            document=document,
            layer_counts=layer_counts,
            block_layer_counts=block_layer_counts,
        ),
        boundary_candidates=_get_boundary_candidates(document),
        blocks=_get_block_references(block_layouts=block_layouts, references=block_references),
        labels_count=labels_count,
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds=bounds,
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _get_layers(
    document: Drawing,
    layer_counts: dict[str, Counter[str]],
    block_layer_counts: dict[str, Counter[str]],
) -> list[AnalysisLayerSchema]:
    layer_names = sorted({layer.dxf.name for layer in document.layers} | set(layer_counts) | set(block_layer_counts))
    layers = []
    for name in layer_names:
        counts = dict(sorted(layer_counts[name].items()))
        block_counts = dict(sorted(block_layer_counts[name].items()))
        combined_counts = Counter(counts)
        combined_counts.update(block_counts)
        is_unused = not combined_counts
        raw_suggestion = suggest_layer(name=name, entity_counts=combined_counts)
        suggestion = (
            AnalysisLayerSuggestionSchema(
                object_type=raw_suggestion.object_type,
                geometry_role=raw_suggestion.geometry_role,
                confidence=raw_suggestion.confidence,
                reason=raw_suggestion.reason,
            )
            if raw_suggestion is not None
            else None
        )
        layers.append(
            AnalysisLayerSchema(
                name=name,
                entity_count=sum(counts.values()),
                entity_counts=counts,
                block_entity_count=sum(block_counts.values()),
                block_entity_counts=block_counts,
                is_unused=is_unused,
                suggestion=suggestion,
            )
        )
    return layers


def _get_boundary_candidates(document: Drawing) -> list[AnalysisBoundaryCandidateSchema]:
    """Возвращает крупнейшие корректные замкнутые полилинии modelspace."""

    ranked: list[tuple[float, int, DXFEntity]] = []
    for ordinal, entity in enumerate(document.modelspace()):
        if entity.dxftype() not in {'LWPOLYLINE', 'POLYLINE'} or not entity.is_closed:
            continue
        raw_coordinates = _raw_polyline_coordinates(entity)
        area = _ring_area(raw_coordinates)
        if area <= 0:
            continue
        item = (area, ordinal, entity)
        if len(ranked) < BOUNDARY_CANDIDATE_LIMIT * 2:
            heappush(ranked, item)
        elif area > ranked[0][0]:
            heapreplace(ranked, item)

    tolerance = _boundary_tolerance(document.units)
    candidates = []
    for _raw_area, ordinal, entity in sorted(ranked, reverse=True):
        candidate = _build_boundary_candidate(entity=entity, ordinal=ordinal, tolerance=tolerance)
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= BOUNDARY_CANDIDATE_LIMIT:
            break
    return candidates


def _raw_polyline_coordinates(entity: DXFEntity) -> list[tuple[float, float]]:
    if entity.dxftype() == 'LWPOLYLINE':
        return [(float(x), float(y)) for x, y in entity.get_points('xy')]
    return [
        (float(vertex.dxf.location.x), float(vertex.dxf.location.y))
        for vertex in islice(entity.vertices, BOUNDARY_COORDINATE_LIMIT * 20)
    ]


def _build_boundary_candidate(
    entity: DXFEntity,
    ordinal: int,
    tolerance: float,
) -> AnalysisBoundaryCandidateSchema | None:
    try:
        vertices = list(make_path(entity).flattening(distance=tolerance, segments=4))
    except (DXFError, ValueError, ArithmeticError, TypeError, NotImplementedError):
        return None
    coordinates = [(float(vertex.x), float(vertex.y)) for vertex in vertices]
    coordinates = _limit_ring_coordinates(coordinates)
    if len(coordinates) < 4:
        return None
    polygon = Polygon(coordinates)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        return None
    handle = entity.dxf.get('handle')
    return AnalysisBoundaryCandidateSchema(
        id=f'{entity.dxftype()}:{handle or ordinal}',
        layer=entity.dxf.get('layer', '0'),
        entity_type=entity.dxftype(),
        area_source_units=polygon.area,
        coordinates=coordinates,
    )


def _limit_ring_coordinates(coordinates: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if coordinates and coordinates[0] == coordinates[-1]:
        coordinates.pop()
    if len(coordinates) > BOUNDARY_COORDINATE_LIMIT - 1:
        step = len(coordinates) / (BOUNDARY_COORDINATE_LIMIT - 1)
        coordinates = [coordinates[int(index * step)] for index in range(BOUNDARY_COORDINATE_LIMIT - 1)]
    if len(set(coordinates)) < 3:
        return []
    return [*coordinates, coordinates[0]]


def _ring_area(coordinates: list[tuple[float, float]]) -> float:
    if len(coordinates) < 3:
        return 0.0
    return (
        abs(
            sum(
                x1 * y2 - x2 * y1
                for (x1, y1), (x2, y2) in zip(coordinates, [*coordinates[1:], coordinates[0]], strict=True)
            )
        )
        / 2
    )


def _boundary_tolerance(unit_code: int) -> float:
    scale_to_meters = UNIT_SCALE_TO_METERS.get(unit_code)
    return 0.1 if scale_to_meters is None else max(0.05 / scale_to_meters, 1e-6)


def _get_block_references(block_layouts, references: Counter[str]) -> dict[str, int]:
    return {block.name: references[block.name] for block in sorted(block_layouts, key=lambda item: item.name)}


def _get_external_references(block_layouts) -> list[str]:
    references = []
    for block in block_layouts:
        if block.block.is_xref:
            references.append(block.block.dxf.get('xref_path', '') or block.name)
    return sorted(set(references))


def _collect_common_entity_stats(
    entity: DXFEntity,
    unsupported_counts: Counter[str],
    block_references: Counter[str],
) -> int:
    entity_type = entity.dxftype()
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        unsupported_counts[entity_type] += 1
    label_count = int(entity_type in LABEL_ENTITY_TYPES)
    if entity_type == 'INSERT':
        block_name = entity.dxf.get('name', '')
        if block_name:
            block_references[block_name] += 1
        label_count += len(entity.attribs)
    return label_count


def _get_modelspace_bounds(document: Drawing) -> tuple[AnalysisBoundsSchema | None, bool]:
    try:
        extents = bbox.extents(document.modelspace(), cache=bbox.Cache())
    except Exception:
        return None, True
    if not extents.has_data:
        return None, False
    return (
        AnalysisBoundsSchema(
            min_x=extents.extmin.x,
            min_y=extents.extmin.y,
            max_x=extents.extmax.x,
            max_y=extents.extmax.y,
        ),
        False,
    )


def _build_warnings(
    document: Drawing,
    entity_counts: dict[str, int],
    external_references: list[str],
    unsupported_entities: dict[str, int],
    bounds_failed: bool,
) -> list[AnalysisWarningSchema]:
    warnings = []
    if document.units == 0:
        warnings.append(
            AnalysisWarningSchema(
                code='units_unspecified',
                message='Единицы измерения чертежа DXF не заданы и требуют подтверждения пользователя',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if external_references:
        warnings.append(
            AnalysisWarningSchema(
                code='external_references',
                message='DXF содержит внешние ссылки, которые нужно разрешить до проверки',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if unsupported_entities:
        warnings.append(
            AnalysisWarningSchema(
                code='unsupported_entities',
                message='DXF содержит типы сущностей, которые не поддерживаются обработкой геометрии',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if not entity_counts:
        warnings.append(
            AnalysisWarningSchema(
                code='empty_drawing',
                message='Листы DXF не содержат графических сущностей',
                severity=AnalysisWarningSeverity.WARNING,
            )
        )
    if bounds_failed:
        warnings.append(
            AnalysisWarningSchema(
                code='bounds_unavailable',
                message='Не удалось полностью вычислить границы пространства модели',
                severity=AnalysisWarningSeverity.WARNING,
            )
        )
    return warnings
