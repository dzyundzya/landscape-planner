import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from yaml import YAMLError

from app.models import PlantingType, SemanticObjectType


class RuleVerificationStatus(StrEnum):
    """Статус проверки нормативного правила."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'
    TEST_ONLY = 'test_only'


class RuleDistanceKind(StrEnum):
    """Способ задания расстояния в нормативном источнике."""

    MINIMUM = 'minimum'
    NOT_SPECIFIED = 'not_specified'


class NormativeRuleSchema(BaseModel):
    """Одно версионированное правило минимального расстояния."""

    id: Annotated[str, Field(min_length=1, max_length=100)]
    version: Annotated[str, Field(min_length=1, max_length=100)]
    object_type: SemanticObjectType
    vegetation_type: PlantingType
    distance_kind: RuleDistanceKind = RuleDistanceKind.MINIMUM
    min_distance_m: Annotated[float, Field(gt=0, le=10_000)] | None = None
    measurement_reference: Annotated[str, Field(min_length=1, max_length=100)]
    conditions: dict[str, JsonValue] = Field(default_factory=dict)
    required_attributes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list)
    document: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    edition: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    clause: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    source_url: Annotated[str | None, Field(min_length=1, max_length=2000)] = None
    verification_status: RuleVerificationStatus
    verified_at: date | None = None
    description: Annotated[str | None, Field(max_length=2000)] = None

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_verification(self) -> 'NormativeRuleSchema':
        """Не допускает verified без полного указания проверенного источника."""

        if self.distance_kind is RuleDistanceKind.MINIMUM and self.min_distance_m is None:
            raise ValueError('Правило минимального расстояния должно содержать числовое значение')
        if self.distance_kind is RuleDistanceKind.NOT_SPECIFIED and self.min_distance_m is not None:
            raise ValueError('При отсутствии числового требования расстояние не задаётся')
        if self.verification_status is RuleVerificationStatus.VERIFIED:
            required = (self.document, self.edition, self.clause, self.source_url, self.verified_at)
            if any(value is None for value in required):
                raise ValueError('Проверенное правило должно содержать документ, редакцию, пункт, URL и дату проверки')
        if len(self.required_attributes) != len(set(self.required_attributes)):
            raise ValueError('Обязательные атрибуты правила не должны повторяться')
        return self


class NormativeRuleSetSchema(BaseModel):
    """Снимок нормативного справочника."""

    schema_version: Annotated[int, Field(ge=1)]
    version: Annotated[str, Field(min_length=1, max_length=100)]
    rules: list[NormativeRuleSchema] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_unique_rules(self) -> 'NormativeRuleSetSchema':
        """Проверяет уникальность ID и версии каждого правила."""

        identities = [(rule.id, rule.version) for rule in self.rules]
        if len(identities) != len(set(identities)):
            raise ValueError('Справочник содержит повторяющиеся ID и версии правил')
        return self


@dataclass(frozen=True, slots=True)
class LoadedRuleSet:
    """Проверенный снимок справочника и его канонический хеш."""

    data: NormativeRuleSetSchema
    sha256: str


class RuleCatalogError(Exception):
    """Нормативный справочник отсутствует или имеет неверный формат."""


def load_rule_set(path: Path) -> LoadedRuleSet:
    """Загружает YAML и вычисляет хеш канонического содержимого."""

    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8'))
        rule_set = NormativeRuleSetSchema.model_validate(payload)
    except (OSError, UnicodeError, YAMLError, ValueError, TypeError) as exc:
        raise RuleCatalogError('Не удалось загрузить нормативный справочник') from exc

    canonical = json.dumps(rule_set.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return LoadedRuleSet(
        data=rule_set,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )
