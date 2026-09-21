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
        }
        for candidate in candidates
    ]
    prompt = (
        'Выбери точки для плана озеленения. Используй только candidate_id из списка и тип из allowed. '
        'Стремись равномерно заполнить участок, сначала достичь лимита деревьев, затем кустарников. '
        'Не повторяй candidate_id. Соблюдай минимальные интервалы.\n'
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
                        'Ты планировщик озеленения. Точные допустимые координаты уже рассчитаны Python. '
                        'Выбирай только из них; не придумывай координаты, нормы или новые точки.'
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
            or not _respects_spacing(
                candidate=candidate, planting_type=choice.type, selected=selected, parameters=parameters
            )
        ):
            rejected += 1
            continue
        used_ids.add(choice.candidate_id)
        counts[choice.type] += 1
        selected.append(GeneratedPlanting(type=choice.type, x_m=candidate.x_m, y_m=candidate.y_m))

    requested_total = parameters.max_trees + parameters.max_bushes
    if requested_total > 0 and not selected:
        raise AgentExecutionError('LLM не выбрал ни одной допустимой посадки')
    warnings = []
    if rejected:
        warnings.append(f'Python отклонил некорректные выборы LLM: {rejected}')
    if counts[PlantingType.TREE] < parameters.max_trees:
        warnings.append('LLM выбрал меньше деревьев, чем заданный лимит')
    if counts[PlantingType.BUSH] < parameters.max_bushes:
        warnings.append('LLM выбрал меньше кустарников, чем заданный лимит')
    return LlmLayoutResult(plantings=tuple(selected), warnings=tuple(warnings), rationale=response.rationale)


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
