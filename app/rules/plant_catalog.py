import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml import YAMLError


class PlantCatalogVerificationStatus(StrEnum):
    """Статус проверки происхождения справочника растений."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'


class PlantAssortment(StrEnum):
    """Раздел исходного ассортимента."""

    PRIMARY = 'primary'
    ADDITIONAL = 'additional'


class PlantGroup(StrEnum):
    """Ботаническая группа в структуре исходной таблицы."""

    CONIFEROUS_TREE = 'coniferous_tree'
    CONIFEROUS_SHRUB = 'coniferous_shrub'
    DECIDUOUS_TREE = 'deciduous_tree'
    DECIDUOUS_SHRUB = 'deciduous_shrub'
    VINE = 'vine'


class TerritoryType(StrEnum):
    """Тип территории из колонок исходной таблицы."""

    COURTYARD = 'courtyard'
    PRESCHOOL = 'preschool'
    EDUCATION_AND_SPORT = 'education_and_sport'
    HEALTHCARE = 'healthcare'
    ROADS = 'roads'
    PUBLIC_AND_COMMERCIAL = 'public_and_commercial'
    PARKS_AND_PUBLIC_GREEN = 'parks_and_public_green'
    INDUSTRIAL_AND_PROTECTION = 'industrial_and_protection'


class PlantSuitability(StrEnum):
    """Рекомендация источника для растения и типа территории."""

    RECOMMENDED = 'recommended'
    NOT_RECOMMENDED = 'not_recommended'
    UNSPECIFIED = 'unspecified'


class PlantCatalogSourceSchema(BaseModel):
    """Происхождение импортированного справочника."""

    title: Annotated[str, Field(min_length=1, max_length=1000)]
    file_name: Annotated[str, Field(min_length=1, max_length=500)]
    file_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    verification_status: PlantCatalogVerificationStatus
    document: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    edition: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    source_url: Annotated[str | None, Field(min_length=1, max_length=2000)] = None
    verified_at: date | None = None

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_verification(self) -> 'PlantCatalogSourceSchema':
        """Не допускает verified без полного описания официального источника."""

        if self.verification_status is PlantCatalogVerificationStatus.VERIFIED:
            required = (self.document, self.edition, self.source_url, self.verified_at)
            if any(value is None for value in required):
                raise ValueError('Проверенный справочник должен содержать документ, редакцию, URL и дату проверки')
        return self


class TerritoryDefinitionSchema(BaseModel):
    """Название территориальной колонки исходного документа."""

    id: TerritoryType
    name_ru: Annotated[str, Field(min_length=1, max_length=500)]
    source_heading: Annotated[str, Field(min_length=1, max_length=2000)]

    model_config = ConfigDict(extra='forbid')


class PlantCatalogNoteSchema(BaseModel):
    """Примечание, на которое ссылаются позиции ассортимента."""

    code: Annotated[str, Field(pattern=r'^[1-9][0-9]*$', max_length=10)]
    text: Annotated[str, Field(min_length=1, max_length=4000)]

    model_config = ConfigDict(extra='forbid')


class PlantCatalogEntrySchema(BaseModel):
    """Одна позиция импортированного ассортимента."""

    id: Annotated[str, Field(pattern=r'^[a-z0-9-]+$', min_length=1, max_length=100)]
    name_ru: Annotated[str, Field(min_length=1, max_length=500)]
    source_name: Annotated[str, Field(min_length=1, max_length=1000)]
    assortment: PlantAssortment
    group: PlantGroup
    forms_and_cultivars: bool = False
    territories: dict[TerritoryType, PlantSuitability]
    note_codes: list[Annotated[str, Field(pattern=r'^[1-9][0-9]*$', max_length=10)]] = Field(default_factory=list)
    source_row: Annotated[int, Field(ge=1)]
    source_number: Annotated[int, Field(ge=1)]

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_territories_and_notes(self) -> 'PlantCatalogEntrySchema':
        """Требует все территориальные колонки и уникальные ссылки на примечания."""

        if set(self.territories) != set(TerritoryType):
            raise ValueError('Позиция справочника должна содержать рекомендацию для каждого типа территории')
        if len(self.note_codes) != len(set(self.note_codes)):
            raise ValueError('Ссылки позиции на примечания не должны повторяться')
        return self


class PlantCatalogSchema(BaseModel):
    """Версионированный справочник рекомендованного ассортимента."""

    schema_version: Annotated[int, Field(ge=1)]
    version: Annotated[str, Field(min_length=1, max_length=100)]
    source: PlantCatalogSourceSchema
    territory_definitions: Annotated[list[TerritoryDefinitionSchema], Field(min_length=1)]
    notes: list[PlantCatalogNoteSchema] = Field(default_factory=list)
    scope_notes: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(default_factory=list)
    plants: Annotated[list[PlantCatalogEntrySchema], Field(min_length=1)]

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_catalog(self) -> 'PlantCatalogSchema':
        """Проверяет уникальность и целостность ссылок всего справочника."""

        territory_ids = [territory.id for territory in self.territory_definitions]
        if len(territory_ids) != len(set(territory_ids)) or set(territory_ids) != set(TerritoryType):
            raise ValueError('Справочник должен определять каждый тип территории ровно один раз')

        note_codes = [note.code for note in self.notes]
        if len(note_codes) != len(set(note_codes)):
            raise ValueError('Коды примечаний справочника не должны повторяться')
        known_note_codes = set(note_codes)

        plant_ids = [plant.id for plant in self.plants]
        if len(plant_ids) != len(set(plant_ids)):
            raise ValueError('ID растений справочника не должны повторяться')
        unknown_note_codes = sorted({code for plant in self.plants for code in plant.note_codes} - known_note_codes)
        if unknown_note_codes:
            raise ValueError(f'Позиции ссылаются на неизвестное примечание {unknown_note_codes[0]}')
        return self


@dataclass(frozen=True, slots=True)
class LoadedPlantCatalog:
    """Проверенный справочник растений и хеш канонического содержимого."""

    data: PlantCatalogSchema
    sha256: str


class PlantCatalogError(Exception):
    """Справочник растений отсутствует или имеет неверный формат."""


def load_plant_catalog(path: Path) -> LoadedPlantCatalog:
    """Загружает YAML-справочник и вычисляет хеш канонического содержимого."""

    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8'))
        catalog = PlantCatalogSchema.model_validate(payload)
    except (OSError, UnicodeError, YAMLError, ValueError, TypeError) as exc:
        raise PlantCatalogError('Не удалось загрузить справочник растений') from exc

    canonical = json.dumps(catalog.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return LoadedPlantCatalog(
        data=catalog,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )
