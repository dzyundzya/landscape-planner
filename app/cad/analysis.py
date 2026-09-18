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

    layout_entities = [entity for layout in document.layouts for entity in layout]
    block_layouts = [block for block in document.blocks if not block.is_any_layout]
    block_entities = [entity for block in block_layouts for entity in block]
    all_entities = [*layout_entities, *block_entities]

    entity_counts = _count_types(layout_entities)
    unsupported_entities = _count_unsupported(all_entities)
    external_references = _get_external_references(block_layouts)
    bounds, bounds_failed = _get_modelspace_bounds(document)
    warnings = _build_warnings(
        document=document,
        entity_counts=entity_counts,
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds_failed=bounds_failed,
    )

    return AnalysisResultSchema(
        dxf_version=document.dxfversion,
        drawing_units=units.decode(document.units),
        entity_counts=entity_counts,
        layers=_get_layers(document=document, entities=layout_entities),
        blocks=_get_block_references(block_layouts=block_layouts, entities=all_entities),
        labels_count=_count_labels(all_entities),
        external_references=external_references,
        unsupported_entities=unsupported_entities,
        bounds=bounds,
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _count_types(entities: list[DXFEntity]) -> dict[str, int]:
    return dict(sorted(Counter(entity.dxftype() for entity in entities).items()))


def _count_unsupported(entities: list[DXFEntity]) -> dict[str, int]:
    return {
        entity_type: count
        for entity_type, count in _count_types(entities).items()
        if entity_type not in SUPPORTED_ENTITY_TYPES
    }


def _get_layers(document: Drawing, entities: list[DXFEntity]) -> list[AnalysisLayerSchema]:
    layer_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for entity in entities:
        layer_counts[entity.dxf.get('layer', '0')][entity.dxftype()] += 1

    layer_names = sorted({layer.dxf.name for layer in document.layers} | set(layer_counts))
    return [
        AnalysisLayerSchema(
            name=name,
            entity_count=sum(layer_counts[name].values()),
            entity_counts=dict(sorted(layer_counts[name].items())),
        )
        for name in layer_names
    ]


def _get_block_references(block_layouts, entities: list[DXFEntity]) -> dict[str, int]:
    references = Counter(
        entity.dxf.get('name', '') for entity in entities if entity.dxftype() == 'INSERT' and entity.dxf.get('name', '')
    )
    return {block.name: references[block.name] for block in sorted(block_layouts, key=lambda item: item.name)}


def _get_external_references(block_layouts) -> list[str]:
    references = []
    for block in block_layouts:
        if block.block.is_xref:
            references.append(block.block.dxf.get('xref_path', '') or block.name)
    return sorted(set(references))


def _count_labels(entities: list[DXFEntity]) -> int:
    count = sum(entity.dxftype() in LABEL_ENTITY_TYPES for entity in entities)
    count += sum(len(entity.attribs) for entity in entities if entity.dxftype() == 'INSERT')
    return count


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
                message='DXF drawing units are not specified and require user confirmation',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if external_references:
        warnings.append(
            AnalysisWarningSchema(
                code='external_references',
                message='DXF contains external references that must be resolved before verification',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if unsupported_entities:
        warnings.append(
            AnalysisWarningSchema(
                code='unsupported_entities',
                message='DXF contains entity types unsupported by the geometry pipeline',
                severity=AnalysisWarningSeverity.BLOCKING,
            )
        )
    if not entity_counts:
        warnings.append(
            AnalysisWarningSchema(
                code='empty_drawing',
                message='DXF layouts do not contain graphical entities',
                severity=AnalysisWarningSeverity.WARNING,
            )
        )
    if bounds_failed:
        warnings.append(
            AnalysisWarningSchema(
                code='bounds_unavailable',
                message='Modelspace bounds could not be calculated completely',
                severity=AnalysisWarningSeverity.WARNING,
            )
        )
    return warnings
