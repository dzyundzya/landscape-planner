import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.models import SemanticObjectType

NAME_SEPARATOR = re.compile(r'[^0-9a-zа-я]+')
EXACT_TOKEN_KEYWORDS = frozenset({'газ', 'кн'})


@dataclass(frozen=True, slots=True)
class LayerSuggestion:
    """Неподтверждённая классификация слоя с объяснением."""

    object_type: SemanticObjectType
    geometry_role: str
    confidence: str
    reason: str


SUGGESTION_RULES: tuple[tuple[SemanticObjectType, str, str, tuple[str, ...]], ...] = (
    (
        SemanticObjectType.UTILITY_GAS,
        'line',
        'high',
        ('газопровод', 'газоснабжение', 'газовая сеть', 'gas pipeline'),
    ),
    (
        SemanticObjectType.UTILITY_SEWER,
        'line',
        'high',
        ('канализация', 'канализ', 'ливневая', 'ливневка', 'дренаж', 'sewer'),
    ),
    (
        SemanticObjectType.UTILITY_WATER,
        'line',
        'high',
        ('водопровод', 'водоснабжение', 'водовод', 'water'),
    ),
    (
        SemanticObjectType.UTILITY_POWER,
        'line',
        'high',
        ('электросеть', 'электрокабель', 'силовой кабель', 'кабельная линия', 'лэп', 'power'),
    ),
    (
        SemanticObjectType.EXISTING_BUSH,
        'area',
        'high',
        ('кустарник', 'кустарники', 'кусты', 'живая изгородь'),
    ),
    (
        SemanticObjectType.EXISTING_TREE,
        'area',
        'high',
        ('дерево', 'деревья', 'древесные', 'дендроплан'),
    ),
    (
        SemanticObjectType.BUILDING,
        'area',
        'high',
        ('здан', 'сооружен', 'строен', 'фундамент', 'building'),
    ),
    (
        SemanticObjectType.ROAD,
        'line',
        'high',
        ('проезжая часть', 'край проезжей', 'бортовой камень', 'бордюр', 'дорога', 'road', 'curb'),
    ),
    (
        SemanticObjectType.OTHER_OBSTACLE,
        'line',
        'medium',
        ('ограждение', 'ограда', 'забор', 'подпорная стена'),
    ),
)

IGNORE_KEYWORDS = (
    'defpoints',
    'размеры',
    'размер',
    'подписи',
    'текст',
    'аннотации',
    'выноски',
    'штриховка',
    'экспликация',
    'таблица',
    'рамка',
    'координатная сетка',
)

MEDIUM_RULES: tuple[tuple[SemanticObjectType, str, tuple[str, ...]], ...] = (
    (SemanticObjectType.UTILITY_POWER, 'line', ('электр', 'кабель', 'эом')),
    (SemanticObjectType.UTILITY_WATER, 'line', ('вода', 'вк вод')),
    (SemanticObjectType.UTILITY_SEWER, 'line', ('сток', 'кн', 'ливн')),
    (SemanticObjectType.UTILITY_GAS, 'line', ('газ',)),
    (SemanticObjectType.BUILDING, 'area', ('стены', 'контур дома', 'архитектура')),
    (SemanticObjectType.ROAD, 'line', ('проезд', 'дорож', 'тротуар', 'покрытие')),
    (SemanticObjectType.EXISTING_BUSH, 'area', ('кустар',)),
    (SemanticObjectType.EXISTING_TREE, 'area', ('дерев', 'озеленение', 'растения')),
)


def suggest_layer(name: str, entity_counts: Mapping[str, int]) -> LayerSuggestion | None:
    """Предлагает назначение слоя без превращения эвристики в подтверждённый факт."""

    normalized = _normalize(name)
    entity_types = {entity_type.upper() for entity_type, count in entity_counts.items() if count > 0}
    if not entity_types:
        return LayerSuggestion(
            object_type=SemanticObjectType.IGNORE,
            geometry_role='line',
            confidence='high',
            reason='Слой не содержит объектов на листах чертежа',
        )
    if any(keyword in normalized for keyword in IGNORE_KEYWORDS) or entity_types <= {
        'ATTDEF',
        'ATTRIB',
        'DIMENSION',
        'LEADER',
        'MLEADER',
        'MTEXT',
        'TEXT',
        'VIEWPORT',
    }:
        return LayerSuggestion(
            object_type=SemanticObjectType.IGNORE,
            geometry_role='line',
            confidence='high',
            reason='Название или состав слоя указывает на оформление чертежа',
        )

    for object_type, geometry_role, confidence, keywords in SUGGESTION_RULES:
        keyword = _find_keyword(normalized=normalized, keywords=keywords)
        if keyword is not None:
            return LayerSuggestion(
                object_type=object_type,
                geometry_role=geometry_role,
                confidence=confidence,
                reason=f'В названии слоя найден признак «{keyword}»',
            )

    for object_type, geometry_role, keywords in MEDIUM_RULES:
        keyword = _find_keyword(normalized=normalized, keywords=keywords)
        if keyword is not None:
            return LayerSuggestion(
                object_type=object_type,
                geometry_role=geometry_role,
                confidence='medium',
                reason=f'Название слоя похоже на категорию по признаку «{keyword}»',
            )
    return None


def _normalize(value: str) -> str:
    return ' '.join(NAME_SEPARATOR.sub(' ', value.casefold().replace('ё', 'е')).split())


def _find_keyword(normalized: str, keywords: tuple[str, ...]) -> str | None:
    tokens = set(normalized.split())
    for keyword in keywords:
        if keyword in EXACT_TOKEN_KEYWORDS:
            if keyword in tokens:
                return keyword
        elif keyword in normalized:
            return keyword
    return None
