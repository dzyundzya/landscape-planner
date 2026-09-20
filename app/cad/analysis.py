import logging
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
from app.cad.normalization import DxfGeometryNormalizer
from app.domain import NormalizationOptions
from app.models import AnalysisWarningSeverity
from app.schemas.analysis import (
    AnalysisBoundaryCandidateSchema,
    AnalysisBoundsSchema,
    AnalysisLayerGeometrySchema,
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
LAYER_PREVIEW_GEOMETRY_LIMIT = 12
LAYER_PREVIEW_COORDINATE_LIMIT = 128
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


class _TransientCopyWarningFilter(logging.Filter):
    """Скрывает предупреждения копирования служебных данных при расчёте bbox."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith('copy process ignored ')


def analyze_dxf(path: Path) -> AnalysisResultSchema:
    """Строит детерминированную диагностическую сводку DXF без бизнес-классификации."""

    try:
        document = ezdxf.readfile(path)
    except (DXFError, OSError, UnicodeError) as exc:
        raise DxfAnalysisError('Не удалось прочитать исходный DXF') from exc

    block_layouts = [block for block in document.blocks if not block.is_any_layout]
    reachable_blocks = _get_reachable_blocks(document)
    entity_counts: Counter[str] = Counter()
    layer_counts: dict[str, Counter[str]] = defaultdict(Counter)
    block_layer_counts: dict[str, Counter[str]] = defaultdict(Counter)
    block_names_by_layer: dict[str, set[str]] = defaultdict(set)
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
    for block in reachable_blocks:
        for entity in block:
            layer_name = entity.dxf.get('layer', '0')
            block_layer_counts[layer_name][entity.dxftype()] += 1
            block_names_by_layer[layer_name].add(block.name)
            labels_count += _collect_common_entity_stats(
                entity=entity,
                unsupported_counts=unsupported_counts,
                block_references=block_references,
            )

    sorted_entity_counts = dict(sorted(entity_counts.items()))
    unsupported_entities = dict(sorted(unsupported_counts.items()))
    external_references = _get_external_references(reachable_blocks)
    bounds, bounds_failed = _get_modelspace_bounds(document)
    warnings = _build_warnings(
        document=document,
        entity_counts=sorted_entity_counts,
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds_failed=bounds_failed,
    )
    layer_previews, truncated_preview_layers = _get_layer_previews(document)

    return AnalysisResultSchema(
        dxf_version=document.dxfversion,
        drawing_units=units.decode(document.units),
        entity_counts=sorted_entity_counts,
        layers=_get_layers(
            document=document,
            layer_counts=layer_counts,
            block_layer_counts=block_layer_counts,
            block_names_by_layer=block_names_by_layer,
            layer_previews=layer_previews,
            truncated_preview_layers=truncated_preview_layers,
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
    block_names_by_layer: dict[str, set[str]],
    layer_previews: dict[str, list[AnalysisLayerGeometrySchema]],
    truncated_preview_layers: frozenset[str],
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
                block_names=sorted(block_names_by_layer[name], key=str.casefold),
                is_unused=is_unused,
                suggestion=suggestion,
                preview=layer_previews.get(name, []),
                preview_truncated=name in truncated_preview_layers,
            )
        )
    return layers


def _get_layer_previews(
    document: Drawing,
) -> tuple[dict[str, list[AnalysisLayerGeometrySchema]], frozenset[str]]:
    """Готовит ограниченную геометрию активных слоёв для браузера."""

    result = DxfGeometryNormalizer(
        options=NormalizationOptions(
            curve_tolerance=_boundary_tolerance(document.units),
            max_geometries_per_layer=LAYER_PREVIEW_GEOMETRY_LIMIT,
            max_points_per_geometry=LAYER_PREVIEW_COORDINATE_LIMIT,
            collect_issues=False,
        )
    ).normalize(document)
    previews: dict[str, list[AnalysisLayerGeometrySchema]] = defaultdict(list)
    for geometry in result.geometries:
        coordinates = [(point.x, point.y) for point in geometry.points]
        if geometry.closed and coordinates[0] != coordinates[-1]:
            if len(coordinates) >= LAYER_PREVIEW_COORDINATE_LIMIT:
                coordinates[-1] = coordinates[0]
            else:
                coordinates.append(coordinates[0])
        previews[geometry.provenance.layer].append(
            AnalysisLayerGeometrySchema(
                entity_type=geometry.provenance.entity_type,
                closed=geometry.closed,
                coordinates=coordinates,
            )
        )
    return dict(previews), result.truncated_layers


def _get_reachable_blocks(document: Drawing) -> list:
    """Находит определения блоков, достижимые из INSERT пространства модели."""

    pending = [entity.dxf.get('name', '') for entity in document.modelspace().query('INSERT')]
    visited = set()
    blocks = []
    while pending:
        name = pending.pop()
        key = name.casefold()
        if not name or key in visited:
            continue
        visited.add(key)
        try:
            block = document.blocks.get(name)
        except DXFError:
            continue
        blocks.append(block)
        pending.extend(entity.dxf.get('name', '') for entity in block.query('INSERT'))
    return blocks


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
    dictionary_logger = logging.getLogger('ezdxf')
    warning_filter = _TransientCopyWarningFilter()
    dictionary_logger.addFilter(warning_filter)
    try:
        extents = bbox.extents(document.modelspace(), fast=True, cache=bbox.Cache())
    except Exception:
        return None, True
    finally:
        dictionary_logger.removeFilter(warning_filter)
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
