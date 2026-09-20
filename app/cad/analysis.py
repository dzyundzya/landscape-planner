from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox, units
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.lldxf.const import DXFError

from app.models import AnalysisWarningSeverity
from app.schemas.analysis import (
    AnalysisBoundsSchema,
    AnalysisLayerSchema,
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
        layers=_get_layers(document=document, layer_counts=layer_counts),
        blocks=_get_block_references(block_layouts=block_layouts, references=block_references),
        labels_count=labels_count,
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds=bounds,
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _get_layers(document: Drawing, layer_counts: dict[str, Counter[str]]) -> list[AnalysisLayerSchema]:
    layer_names = sorted({layer.dxf.name for layer in document.layers} | set(layer_counts))
    return [
        AnalysisLayerSchema(
            name=name,
            entity_count=sum(layer_counts[name].values()),
            entity_counts=dict(sorted(layer_counts[name].items())),
        )
        for name in layer_names
    ]


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
