import hashlib
import re
from collections import defaultdict

from app.schemas.analysis import AnalysisLayerGroupSchema, AnalysisLayerSchema

FAMILY_SUFFIX = re.compile(r'(?<=[0-9a-zа-я_])[0-9a-f]$', re.IGNORECASE)


def build_layer_groups(layers: list[AnalysisLayerSchema]) -> list[AnalysisLayerGroupSchema]:
    """Группирует активные слои для подтверждения без автоматической классификации."""

    active_layers = [layer for layer in layers if not layer.is_unused]
    suggested: dict[tuple[str, str, str], list[AnalysisLayerSchema]] = defaultdict(list)
    unresolved = []
    for layer in active_layers:
        if layer.suggestion is None or layer.suggestion.object_type.value == 'ignore':
            unresolved.append(layer)
            continue
        suggestion = layer.suggestion
        suggested[(suggestion.object_type.value, suggestion.geometry_role, suggestion.confidence)].append(layer)

    groups = [_suggested_group(key=key, layers=group_layers) for key, group_layers in sorted(suggested.items())]
    families: dict[str, list[AnalysisLayerSchema]] = defaultdict(list)
    for layer in unresolved:
        families[_family_key(layer.name)].append(layer)
    groups.extend(
        _family_group(key=key, layers=group_layers)
        for key, group_layers in sorted(families.items())
        if len(group_layers) > 1
    )
    return groups


def _suggested_group(
    key: tuple[str, str, str],
    layers: list[AnalysisLayerSchema],
) -> AnalysisLayerGroupSchema:
    suggestion = layers[0].suggestion
    if suggestion is None:  # pragma: no cover - защищает внутренний контракт группировки
        raise ValueError('Группа предложений должна содержать рекомендацию')
    confidence_label = 'высокая уверенность' if suggestion.confidence == 'high' else 'требуется проверка'
    return AnalysisLayerGroupSchema(
        id=_group_id('suggested', ':'.join(key)),
        label=f'{suggestion.object_type.value}: {confidence_label}',
        kind='suggested',
        layer_names=sorted((layer.name for layer in layers), key=str.casefold),
        suggestion=suggestion,
        reason=(
            f'{len(layers)} слоёв получили одинаковую рекомендацию по названию и составу. '
            'Перед массовым применением проверьте их геометрию.'
        ),
    )


def _family_group(key: str, layers: list[AnalysisLayerSchema]) -> AnalysisLayerGroupSchema:
    display_name = _display_name(layers[0].name)
    if FAMILY_SUFFIX.search(display_name):
        display_name = f'{display_name[:-1]}*'
    return AnalysisLayerGroupSchema(
        id=_group_id('family', key),
        label=display_name,
        kind='family',
        layer_names=sorted((layer.name for layer in layers), key=str.casefold),
        reason=(
            'Названия отличаются только конечным индексом. Семейство показано вместе для проверки, '
            'но его назначение не определено автоматически.'
        ),
    )


def _family_key(name: str) -> str:
    return FAMILY_SUFFIX.sub('*', _display_name(name).casefold().replace('ё', 'е'))


def _display_name(name: str) -> str:
    return name.rsplit('$0$', maxsplit=1)[-1]


def _group_id(kind: str, key: str) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f'{kind}:{digest}'
