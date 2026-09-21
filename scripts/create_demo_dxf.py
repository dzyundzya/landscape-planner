from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

OUTPUT_PATH = Path(__file__).resolve().parents[1] / 'examples' / 'greenplan_demo.dxf'

BOUNDARY_LAYER = 'РАМКА_ГРАНИЦА_УЧАСТКА'
BUILDING_LAYER = 'ЗДАНИЕ'
ROAD_LAYER = 'КРАЙ_ДОРОГИ'
WATER_LAYER = 'ВОДОПРОВОД'
POWER_LAYER = 'ЭЛЕКТРОКАБЕЛЬ'
TREE_LAYER = 'СУЩЕСТВУЮЩИЕ_ДЕРЕВЬЯ'
LABEL_LAYER = 'ПОДПИСИ'


def create_demo_dxf(output_path: Path = OUTPUT_PATH) -> Path:
    """Создаёт небольшую метровую DXF-подоснову для сквозной демонстрации."""

    document = ezdxf.new('R2010', setup=True)
    document.units = units.M
    document.header['$MEASUREMENT'] = 1

    _add_layers(document)
    modelspace = document.modelspace()

    # Самый крупный замкнутый контур станет первым кандидатом границы в UI.
    modelspace.add_lwpolyline(
        [(0, 0), (100, 0), (100, 60), (0, 60)],
        close=True,
        dxfattribs={'layer': BOUNDARY_LAYER, 'lineweight': 35},
    )

    modelspace.add_lwpolyline(
        [(10, 36), (30, 36), (30, 52), (10, 52)],
        close=True,
        dxfattribs={'layer': BUILDING_LAYER},
    )

    # Две линии задают края проезжей части.
    modelspace.add_line((0, 10), (100, 10), dxfattribs={'layer': ROAD_LAYER})
    modelspace.add_line((0, 18), (100, 18), dxfattribs={'layer': ROAD_LAYER})

    modelspace.add_lwpolyline(
        [(5, 27), (40, 27), (58, 32), (95, 32)],
        dxfattribs={'layer': WATER_LAYER},
    )
    modelspace.add_lwpolyline(
        [(52, 4), (52, 24), (70, 42), (96, 42)],
        dxfattribs={'layer': POWER_LAYER},
    )

    for center, radius in (((39, 46), 2.5), ((48, 50), 2.0), ((78, 49), 3.0)):
        modelspace.add_circle(center=center, radius=radius, dxfattribs={'layer': TREE_LAYER})

    _add_label(modelspace, 'Демо-участок Greenplan, 100 x 60 м', (50, 57))
    _add_label(modelspace, 'Здание', (20, 44))
    _add_label(modelspace, 'Дорога', (50, 14))
    _add_label(modelspace, 'Водопровод', (25, 28.5))
    _add_label(modelspace, 'Подземный электрокабель', (73, 40))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(output_path)
    return output_path


def _add_layers(document: ezdxf.document.Drawing) -> None:
    layers = (
        (BOUNDARY_LAYER, 7),
        (BUILDING_LAYER, 1),
        (ROAD_LAYER, 8),
        (WATER_LAYER, 5),
        (POWER_LAYER, 2),
        (TREE_LAYER, 3),
        (LABEL_LAYER, 7),
    )
    for name, color in layers:
        document.layers.add(name=name, color=color)


def _add_label(modelspace, text: str, position: tuple[float, float]) -> None:
    modelspace.add_text(
        text,
        height=1.2,
        dxfattribs={'layer': LABEL_LAYER},
    ).set_placement(position, align=TextEntityAlignment.MIDDLE_CENTER)


if __name__ == '__main__':
    created_path = create_demo_dxf()
    print(created_path)
