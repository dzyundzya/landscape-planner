from collections.abc import Iterable

from app.models import PlantingType, TerritoryType
from app.rules import LoadedPlantCatalog, PlantAssortment, PlantGroup, PlantSuitability

PLANT_GROUPS_BY_TYPE = {
    PlantingType.TREE: frozenset((PlantGroup.CONIFEROUS_TREE, PlantGroup.DECIDUOUS_TREE)),
    PlantingType.BUSH: frozenset((PlantGroup.CONIFEROUS_SHRUB, PlantGroup.DECIDUOUS_SHRUB)),
}


class SpeciesSelectionError(Exception):
    """Для типа посадки нет однозначно рекомендованных позиций справочника."""


def assign_species(
    planting_types: Iterable[PlantingType],
    catalog: LoadedPlantCatalog,
    territory_type: TerritoryType,
) -> tuple[str, ...]:
    """Детерминированно распределяет однозначно рекомендованные породы по посадкам."""

    requested_types = tuple(planting_types)
    candidates = {
        planting_type: _eligible_names(
            catalog=catalog,
            territory_type=territory_type,
            planting_type=planting_type,
        )
        for planting_type in set(requested_types)
    }
    missing_type = next((planting_type for planting_type, names in candidates.items() if not names), None)
    if missing_type is not None:
        raise SpeciesSelectionError(f'Для типа посадки {missing_type.value} нет однозначно рекомендованных растений')

    indexes = {planting_type: 0 for planting_type in candidates}
    assigned = []
    for planting_type in requested_types:
        names = candidates[planting_type]
        index = indexes[planting_type]
        assigned.append(names[index % len(names)])
        indexes[planting_type] = index + 1
    return tuple(assigned)


def _eligible_names(
    catalog: LoadedPlantCatalog,
    territory_type: TerritoryType,
    planting_type: PlantingType,
) -> tuple[str, ...]:
    assortment_order = {PlantAssortment.PRIMARY: 0, PlantAssortment.ADDITIONAL: 1}
    entries = (
        plant
        for plant in catalog.data.plants
        if plant.group in PLANT_GROUPS_BY_TYPE[planting_type]
        and plant.territories[territory_type] is PlantSuitability.RECOMMENDED
        and not plant.note_codes
    )
    ordered = sorted(entries, key=lambda plant: (assortment_order[plant.assortment], plant.id))
    return tuple(plant.name_ru for plant in ordered)
