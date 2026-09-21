from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.lldxf.const import DXF2000, DXFError
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from app.domain import CoordinateTransform, Point2D
from app.geometry import RestrictionResult
from app.models import PlantingType
from app.schemas.planting import PlantingReadSchema

EXPORT_DXF_VERSION = 'dxf-export/3'
LAYER_DEFINITIONS = {
    'trees': ('GREENPLAN_TREES', 3),
    'bushes': ('GREENPLAN_BUSHES', 94),
    'tree_labels': ('GREENPLAN_TREE_LABELS', 3),
    'bush_labels': ('GREENPLAN_BUSH_LABELS', 94),
    'tree_available': ('GREENPLAN_TREE_AVAILABLE', 92),
    'bush_available': ('GREENPLAN_BUSH_AVAILABLE', 72),
    'tree_exclusion': ('GREENPLAN_TREE_EXCLUSION', 1),
    'bush_exclusion': ('GREENPLAN_BUSH_EXCLUSION', 30),
    'legend': ('GREENPLAN_LEGEND', 7),
}
DRAFT_LAYER_DEFINITION = ('GREENPLAN_DRAFT', 1)
BLOCK_DEFINITIONS = {
    PlantingType.TREE: ('GREENPLAN_TREE', 0.5),
    PlantingType.BUSH: ('GREENPLAN_BUSH', 0.3),
}


class DxfExportError(Exception):
    """Итоговый DXF не удалось сформировать или проверить."""


@dataclass(frozen=True, slots=True)
class DxfExportMetadata:
    """Фактически использованные имена новых слоёв и блоков."""

    layers: dict[str, str]
    blocks: dict[PlantingType, str]


def write_landscape_dxf(
    source_path: Path,
    output_path: Path,
    plantings: list[PlantingReadSchema],
    transform: CoordinateTransform,
    restrictions: RestrictionResult,
    *,
    draft: bool = False,
) -> DxfExportMetadata:
    """Копирует исходный DXF и добавляет посадки и расчётные зоны."""

    try:
        document = ezdxf.readfile(source_path)
        source_entities = _entity_identity(document)
        layers = _create_layers(document=document)
        blocks = _create_blocks(document=document, transform=transform)
        modelspace = document.modelspace()

        if draft:
            layers['draft'] = _add_draft_notice(document=document, restrictions=restrictions, transform=transform)

        counters = {PlantingType.TREE: 0, PlantingType.BUSH: 0}
        legend_entries = []
        for planting in plantings:
            point = transform.to_source(Point2D(x=float(planting.x_m), y=float(planting.y_m)))
            is_tree = planting.type is PlantingType.TREE
            layer = layers['trees' if is_tree else 'bushes']
            label_layer = layers['tree_labels' if is_tree else 'bush_labels']
            counters[planting.type] += 1
            mark = f'{"Д" if is_tree else "К"}-{counters[planting.type]:03d}'
            insert = modelspace.add_blockref(
                blocks[planting.type],
                (point.x, point.y),
                dxfattribs={'layer': layer},
            )
            insert.add_auto_attribs(
                {
                    'PLANTING_ID': str(planting.public_id),
                    'PLANTING_TYPE': planting.type.value,
                    'SPECIES': planting.species or '',
                    'MARK': mark,
                }
            )
            _add_planting_label(
                document=document,
                point=point,
                mark=mark,
                layer=label_layer,
                transform=transform,
                planting_type=planting.type,
            )
            legend_entries.append((mark, planting.species))

        _add_geometry(document, restrictions.tree_available, layers['tree_available'], transform)
        _add_geometry(document, restrictions.bush_available, layers['bush_available'], transform)
        _add_geometry(document, restrictions.tree_exclusion, layers['tree_exclusion'], transform)
        _add_geometry(document, restrictions.bush_exclusion, layers['bush_exclusion'], transform)
        _add_planting_legend(
            document=document,
            entries=legend_entries,
            restrictions=restrictions,
            layer=layers['legend'],
            transform=transform,
        )
        document.saveas(output_path)
        _verify_output(
            output_path=output_path,
            source_entities=source_entities,
            planting_ids={str(planting.public_id) for planting in plantings},
            layers=set(layers.values()),
            blocks=set(blocks.values()),
        )
    except (DXFError, OSError, UnicodeError, ValueError, TypeError) as exc:
        raise DxfExportError('Не удалось сформировать итоговый DXF') from exc
    return DxfExportMetadata(layers=layers, blocks=blocks)


def _add_draft_notice(
    document: Drawing,
    restrictions: RestrictionResult,
    transform: CoordinateTransform,
) -> str:
    """Добавляет в DXF видимую маркировку демонстрационного результата."""

    existing = {layer.dxf.name.casefold() for layer in document.layers}
    layer_name = _unique_name(preferred=DRAFT_LAYER_DEFINITION[0], existing=existing)
    document.layers.add(name=layer_name, color=DRAFT_LAYER_DEFINITION[1])

    available = restrictions.tree_available.union(restrictions.bush_available)
    x_m, y_m = (0.0, 0.0) if available.is_empty else (available.bounds[0], available.bounds[3])
    point = transform.to_source(Point2D(x=x_m, y=y_m))
    document.modelspace().add_mtext(
        'ДЕМОНСТРАЦИОННЫЙ ЧЕРНОВИК. НОРМАТИВНЫЕ ПРАВИЛА ТРЕБУЮТ ПОДТВЕРЖДЕНИЯ.',
        dxfattribs={
            'insert': (point.x, point.y),
            'char_height': max(1.5 / transform.scale_to_meters, 1e-9),
            'layer': layer_name,
        },
    )
    return layer_name


def _create_layers(document: Drawing) -> dict[str, str]:
    existing = {layer.dxf.name.casefold() for layer in document.layers}
    names = {}
    for key, (preferred_name, color) in LAYER_DEFINITIONS.items():
        name = _unique_name(preferred=preferred_name, existing=existing)
        layer = document.layers.add(name=name, color=color)
        if key.endswith(('_available', '_exclusion')):
            layer.off()
        existing.add(name.casefold())
        names[key] = name
    return names


def _create_blocks(document: Drawing, transform: CoordinateTransform) -> dict[PlantingType, str]:
    existing = {block.name.casefold() for block in document.blocks}
    names = {}
    for planting_type, (preferred_name, radius_m) in BLOCK_DEFINITIONS.items():
        name = _unique_name(preferred=preferred_name, existing=existing)
        block = document.blocks.new(name=name)
        radius = radius_m / transform.scale_to_meters
        block.add_circle((0, 0), radius=radius)
        if planting_type is PlantingType.TREE:
            block.add_line((-radius, 0), (radius, 0))
            block.add_line((0, -radius), (0, radius))
        else:
            block.add_circle((0, 0), radius=radius * 0.55)
            block.add_line((-radius * 0.7, -radius * 0.7), (radius * 0.7, radius * 0.7))
            block.add_line((-radius * 0.7, radius * 0.7), (radius * 0.7, -radius * 0.7))
        attribute_height = max(radius * 0.25, 1e-9)
        for tag in ('PLANTING_ID', 'PLANTING_TYPE', 'SPECIES', 'MARK'):
            block.add_attdef(
                tag=tag,
                insert=(0, 0),
                height=attribute_height,
                dxfattribs={'flags': 1},
            )
        existing.add(name.casefold())
        names[planting_type] = name
    return names


def _add_planting_label(
    document: Drawing,
    point: Point2D,
    mark: str,
    layer: str,
    transform: CoordinateTransform,
    planting_type: PlantingType,
) -> None:
    """Добавляет рядом с посадкой компактную видимую марку."""

    offset_m = 0.55 if planting_type is PlantingType.TREE else 0.4
    offset = offset_m / transform.scale_to_meters
    height = max(0.25 / transform.scale_to_meters, 1e-9)
    document.modelspace().add_text(
        mark,
        dxfattribs={
            'insert': (point.x + offset, point.y + offset),
            'height': height,
            'layer': layer,
        },
    )


def _add_planting_legend(
    document: Drawing,
    entries: list[tuple[str, str | None]],
    restrictions: RestrictionResult,
    layer: str,
    transform: CoordinateTransform,
) -> None:
    """Добавляет за границей участка расшифровку марок посадок."""

    if not entries:
        return
    available = restrictions.tree_available.union(restrictions.bush_available)
    if available.is_empty:
        x_m = 2.0
        y_m = 0.0
    else:
        _, _, max_x, max_y = available.bounds
        x_m = max_x + 2.0
        y_m = max_y
    point = transform.to_source(Point2D(x=x_m, y=y_m))
    rows = ['ЭКСПЛИКАЦИЯ ПОСАДОК']
    rows.extend(f'{mark} — {species or "порода не указана"}' for mark, species in entries)
    document.modelspace().add_mtext(
        '\\P'.join(rows),
        dxfattribs={
            'insert': (point.x, point.y),
            'char_height': max(0.4 / transform.scale_to_meters, 1e-9),
            'width': max(35.0 / transform.scale_to_meters, 1e-9),
            'layer': layer,
        },
    )


def _add_geometry(
    document: Drawing,
    geometry: BaseGeometry,
    layer: str,
    transform: CoordinateTransform,
) -> None:
    for polygon in _iter_polygons(geometry):
        _add_ring(document=document, coordinates=polygon.exterior.coords, layer=layer, transform=transform)
        for interior in polygon.interiors:
            _add_ring(document=document, coordinates=interior.coords, layer=layer, transform=transform)


def _add_ring(document: Drawing, coordinates, layer: str, transform: CoordinateTransform) -> None:
    points = []
    for x, y, *_ in coordinates:
        source = transform.to_source(Point2D(x=float(x), y=float(y)))
        points.append((source.x, source.y))
    if len(points) < 4:
        return
    if points[0] == points[-1]:
        points.pop()
    attributes = {'layer': layer}
    if document.dxfversion >= DXF2000:
        document.modelspace().add_lwpolyline(points, close=True, dxfattribs=attributes)
    else:
        document.modelspace().add_polyline2d(points, close=True, dxfattribs=attributes)


def _iter_polygons(geometry: BaseGeometry):
    if geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon | GeometryCollection):
        for child in geometry.geoms:
            yield from _iter_polygons(child)


def _verify_output(
    output_path: Path,
    source_entities: set[tuple[str, str]],
    planting_ids: set[str],
    layers: set[str],
    blocks: set[str],
) -> None:
    document = ezdxf.readfile(output_path)
    if not source_entities.issubset(_entity_identity(document)):
        raise DxfExportError('Итоговый DXF потерял исходные сущности modelspace')
    actual_layers = {layer.dxf.name for layer in document.layers}
    if not layers.issubset(actual_layers):
        raise DxfExportError('Итоговый DXF не содержит все расчётные слои')
    actual_ids = {
        attribute.dxf.text
        for insert in document.modelspace().query('INSERT')
        if insert.dxf.name in blocks
        for attribute in insert.attribs
        if attribute.dxf.tag == 'PLANTING_ID'
    }
    if actual_ids != planting_ids:
        raise DxfExportError('Итоговый DXF содержит неполный набор идентификаторов посадок')


def _entity_identity(document: Drawing) -> set[tuple[str, str]]:
    return {
        (entity.dxf.handle, entity.dxftype())
        for entity in document.modelspace()
        if entity.dxf.get('handle') is not None
    }


def _unique_name(preferred: str, existing: set[str]) -> str:
    if preferred.casefold() not in existing:
        return preferred
    suffix = 1
    while f'{preferred}_{suffix}'.casefold() in existing:
        suffix += 1
    return f'{preferred}_{suffix}'
