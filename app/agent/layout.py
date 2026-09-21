import json
import math
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agent.model import build_chat_model
from app.core.config.settings.base_settings import BackendSettings
from app.models import PlantingType
from app.planning.generator import GeneratedPlanting, LayoutCandidate
from app.schemas.config_snapshot import GenerationParametersSchema
from app.services.exceptions.agents import AgentExecutionError

LLM_LAYOUT_VERSION = 'langchain-candidate-selection/1'
MAX_LLM_PLANTINGS = 200


class LlmPlacementChoice(BaseModel):
    """Выбор одной посадки из подготовленных Python кандидатов."""

    candidate_id: int = Field(ge=0)
    type: PlantingType

    model_config = ConfigDict(extra='forbid')


class LlmLayoutResponse(BaseModel):
    """Структурированный ответ LLM с выбором точек посадки."""

    placements: list[LlmPlacementChoice] = Field(max_length=MAX_LLM_PLANTINGS)
    rationale: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra='forbid')


@dataclass(frozen=True, slots=True)
class LlmLayoutResult:
    """Проверенная выборка посадок модели."""

    plantings: tuple[GeneratedPlanting, ...]
    warnings: tuple[str, ...]
    rationale: str


def select_llm_layout(
    candidates: tuple[LayoutCandidate, ...],
    parameters: GenerationParametersSchema,
    settings: BackendSettings,
) -> LlmLayoutResult:
    """Предлагает LLM выбрать посадки и повторно проверяет выбор в Python."""

    if not candidates:
        return LlmLayoutResult(plantings=(), warnings=('Нет допустимых точек для LLM-планировщика',), rationale='')

    model = build_chat_model(settings=settings).with_structured_output(LlmLayoutResponse)
    candidate_payload = [
        {
            'id': candidate.id,
            'x': candidate.x_m,
            'y': candidate.y_m,
            'allowed': [planting_type.value for planting_type in candidate.allowed_types],
            'roles': list(candidate.design_roles),
            'road_m': candidate.distance_to_road_m,
            'building_m': candidate.distance_to_building_m,
            'boundary_m': round(candidate.distance_to_boundary_m, 3),
        }
        for candidate in candidates
    ]
    prompt = (
        'Выбери точки для плана озеленения. Используй только candidate_id из списка и тип из allowed. '
        'Создай связную ландшафтную композицию, а не случайное заполнение. '
        'Для аллей выбирай деревья с role=road_alley последовательными рядами вдоль дороги. '
        'Около зданий выбирай деревья для тени и кустарники с role=building_edge. '
        'Кустарники также можно собирать по role=perimeter. Точки open_space используй только для '
        'осмысленных групп или когда профильных точек недостаточно. Не чередуй дерево и куст случайно. '
        'Выбирай регулярные последовательности координат и не повторяй candidate_id. Соблюдай интервалы.\n'
        f'Лимиты: trees={min(parameters.max_trees, MAX_LLM_PLANTINGS)}, '
        f'bushes={min(parameters.max_bushes, MAX_LLM_PLANTINGS)}, '
        f'tree_tree={parameters.tree_tree_distance_m}, bush_bush={parameters.bush_bush_distance_m}, '
        f'tree_bush={parameters.tree_bush_distance_m}.\n'
        f'Кандидаты: {json.dumps(candidate_payload, ensure_ascii=False, separators=(",", ":"))}'
    )
    try:
        response = model.invoke(
            [
                SystemMessage(
                    content=(
                        'Ты ландшафтный проектировщик. Точные допустимые координаты и их связь с дорогами, '
                        'зданиями и границей уже рассчитаны Python. Проектируй аллеи деревьев, озеленение '
                        'вокруг зданий и цельные группы кустарников. Выбирай только переданные точки; '
                        'не придумывай координаты, нормы или новые точки.'
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        raise AgentExecutionError('LLM не смог сформировать план посадок') from exc
    if not isinstance(response, LlmLayoutResponse):
        raise AgentExecutionError('LLM вернул некорректную структуру плана')
    return _validate_choices(response=response, candidates=candidates, parameters=parameters)


def _validate_choices(
    response: LlmLayoutResponse,
    candidates: tuple[LayoutCandidate, ...],
    parameters: GenerationParametersSchema,
) -> LlmLayoutResult:
    candidate_index = {candidate.id: candidate for candidate in candidates}
    selected: list[GeneratedPlanting] = []
    used_ids: set[int] = set()
    rejected = 0
    counts = {PlantingType.TREE: 0, PlantingType.BUSH: 0}
    limits = {
        PlantingType.TREE: min(parameters.max_trees, MAX_LLM_PLANTINGS),
        PlantingType.BUSH: min(parameters.max_bushes, MAX_LLM_PLANTINGS),
    }
    for choice in response.placements:
        candidate = candidate_index.get(choice.candidate_id)
        if (
            candidate is None
            or choice.candidate_id in used_ids
            or choice.type not in candidate.allowed_types
            or counts[choice.type] >= limits[choice.type]
            or not _matches_composition_role(candidate=candidate, planting_type=choice.type, candidates=candidates)
            or not _respects_spacing(
                candidate=candidate, planting_type=choice.type, selected=selected, parameters=parameters
            )
        ):
            rejected += 1
            continue
        used_ids.add(choice.candidate_id)
        counts[choice.type] += 1
        selected.append(GeneratedPlanting(type=choice.type, x_m=candidate.x_m, y_m=candidate.y_m))

    filled = _fill_composition(
        candidates=candidates,
        selected=selected,
        used_ids=used_ids,
        counts=counts,
        limits=limits,
        parameters=parameters,
    )

    requested_total = parameters.max_trees + parameters.max_bushes
    if requested_total > 0 and not selected:
        raise AgentExecutionError('LLM не выбрал ни одной допустимой посадки')
    warnings = []
    if rejected:
        warnings.append(f'Python отклонил некорректные выборы LLM: {rejected}')
    if filled:
        warnings.append(f'Python дополнил композицию профильными точками: {filled}')
    if counts[PlantingType.TREE] < parameters.max_trees:
        warnings.append('LLM выбрал меньше деревьев, чем заданный лимит')
    if counts[PlantingType.BUSH] < parameters.max_bushes:
        warnings.append('LLM выбрал меньше кустарников, чем заданный лимит')
    return LlmLayoutResult(plantings=tuple(selected), warnings=tuple(warnings), rationale=response.rationale)


def _matches_composition_role(
    candidate: LayoutCandidate,
    planting_type: PlantingType,
    candidates: tuple[LayoutCandidate, ...],
) -> bool:
    preferred_roles = _preferred_roles(planting_type=planting_type)
    has_preferred = any(
        planting_type in item.allowed_types and preferred_roles.intersection(item.design_roles) for item in candidates
    )
    return not has_preferred or bool(preferred_roles.intersection(candidate.design_roles))


def _fill_composition(
    candidates: tuple[LayoutCandidate, ...],
    selected: list[GeneratedPlanting],
    used_ids: set[int],
    counts: dict[PlantingType, int],
    limits: dict[PlantingType, int],
    parameters: GenerationParametersSchema,
) -> int:
    filled = 0
    for planting_type in (PlantingType.TREE, PlantingType.BUSH):
        ranked = sorted(
            (candidate for candidate in candidates if planting_type in candidate.allowed_types),
            key=lambda candidate: _composition_rank(candidate=candidate, planting_type=planting_type),
        )
        for candidate in ranked:
            if counts[planting_type] >= limits[planting_type]:
                break
            if candidate.id in used_ids or not _respects_spacing(
                candidate=candidate,
                planting_type=planting_type,
                selected=selected,
                parameters=parameters,
            ):
                continue
            selected.append(GeneratedPlanting(type=planting_type, x_m=candidate.x_m, y_m=candidate.y_m))
            used_ids.add(candidate.id)
            counts[planting_type] += 1
            filled += 1
    return filled


def _preferred_roles(planting_type: PlantingType) -> set[str]:
    if planting_type is PlantingType.TREE:
        return {'road_alley', 'building_edge'}
    return {'building_edge', 'perimeter'}


def _composition_rank(candidate: LayoutCandidate, planting_type: PlantingType) -> tuple[float, float, float, float]:
    if planting_type is PlantingType.TREE:
        primary = (
            min(
                value for value in (candidate.distance_to_road_m, candidate.distance_to_building_m) if value is not None
            )
            if candidate.distance_to_road_m is not None or candidate.distance_to_building_m is not None
            else float('inf')
        )
        role_rank = (
            0 if 'road_alley' in candidate.design_roles else 1 if 'building_edge' in candidate.design_roles else 2
        )
    else:
        primary = (
            candidate.distance_to_building_m
            if candidate.distance_to_building_m is not None
            else candidate.distance_to_boundary_m
        )
        role_rank = (
            0 if 'building_edge' in candidate.design_roles else 1 if 'perimeter' in candidate.design_roles else 2
        )
    return role_rank, primary, candidate.y_m, candidate.x_m


def _respects_spacing(
    candidate: LayoutCandidate,
    planting_type: PlantingType,
    selected: list[GeneratedPlanting],
    parameters: GenerationParametersSchema,
) -> bool:
    for other in selected:
        if planting_type is PlantingType.TREE and other.type is PlantingType.TREE:
            required = parameters.tree_tree_distance_m
        elif planting_type is PlantingType.BUSH and other.type is PlantingType.BUSH:
            required = parameters.bush_bush_distance_m
        else:
            required = parameters.tree_bush_distance_m
        if math.hypot(candidate.x_m - other.x_m, candidate.y_m - other.y_m) + 1e-9 < required:
            return False
    return True
