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

LLM_LAYOUT_VERSION = 'langchain-candidate-selection/4'
MAX_LLM_PLANTINGS = 200
MAX_LAYOUT_ATTEMPTS = 3
LANDSCAPE_LAYOUT_SYSTEM_PROMPT = """Ты ведущий ландшафтный архитектор городских территорий.
Тебе переданы только допустимые точки, уже рассчитанные Python с учётом геометрии и нормативных ограничений.
Твоя задача — выбрать из них понятную композицию, которую проектировщик сможет объяснить на плане.

Сначала мысленно выбери два–четыре композиционных элемента, затем подбери точки для них:
1. Основной ряд или аллея деревьев вдоль дороги. Используй точки road_alley, лежащие в одной линии или
   образующие плавную последовательность, с визуально равномерным шагом.
2. При необходимости второй короткий ряд деревьев или компактную группу у здания из точек building_edge.
3. Две–четыре компактные группы кустарников по три–семь растений у здания или границы участка.
4. Точки open_space используй только для отдельной компактной группы, а не для заполнения пустот.

Не разбрасывай одиночные растения по всей территории, не создавай шахматное поле и не чередуй случайно деревья
и кустарники. Размести ровно указанное целевое количество каждого типа, сохранив ритм, группы, свободные проходы
и читаемую структуру. Не придумывай входы в здание, стороны света, координаты, нормы или новые точки: этих данных
у тебя нет. Используй только переданные candidate_id и allowed. Верни сначала все деревья, затем все кустарники.
В rationale по-русски назови выбранные композиционные элементы и объясни, почему они образуют цельный план."""


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

    target_counts = _target_counts(parameters=parameters)
    if not candidates:
        if sum(target_counts.values()) > 0:
            raise AgentExecutionError('Нет допустимых точек для размещения целевого количества растений')
        return LlmLayoutResult(plantings=(), warnings=(), rationale='Посадки не запрошены')

    model = build_chat_model(settings=settings).with_structured_output(LlmLayoutResponse)
    candidate_index = {candidate.id: candidate for candidate in candidates}
    selected: list[GeneratedPlanting] = []
    used_ids: set[int] = set()
    warnings: list[str] = []
    rationales: list[str] = []
    received_response = False
    for attempt in range(1, MAX_LAYOUT_ATTEMPTS + 1):
        current_counts = _planting_counts(plantings=tuple(selected))
        remaining_counts = {
            planting_type: target_counts[planting_type] - current_counts[planting_type]
            for planting_type in PlantingType
        }
        if not any(remaining_counts.values()):
            return _build_accumulated_result(
                selected=selected,
                warnings=warnings,
                rationales=rationales,
                attempts=attempt - 1,
            )
        candidate_payload = _candidate_payload_for_addition(
            candidates=candidates,
            selected=selected,
            used_ids=used_ids,
            remaining_counts=remaining_counts,
            parameters=parameters,
        )
        if not candidate_payload:
            break
        prompt = _build_addition_prompt(
            candidate_payload=candidate_payload,
            selected=selected,
            used_ids=used_ids,
            remaining_counts=remaining_counts,
            parameters=parameters,
        )
        try:
            response = model.invoke(
                [
                    SystemMessage(content=LANDSCAPE_LAYOUT_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
        except Exception as exc:
            if not received_response:
                raise AgentExecutionError('LLM не смог сформировать план посадок') from exc
            warnings.append('Повторное обращение к LLM завершилось ошибкой; применено алгоритмическое дополнение')
            break
        if not isinstance(response, LlmLayoutResponse):
            if not received_response:
                raise AgentExecutionError('LLM вернул некорректную структуру плана')
            warnings.append('Повторный ответ LLM имел неверную структуру; применено алгоритмическое дополнение')
            break
        received_response = True
        additions, accepted_ids = _validate_additions(
            response=response,
            candidate_index=candidate_index,
            selected=selected,
            used_ids=used_ids,
            remaining_counts=remaining_counts,
            parameters=parameters,
        )
        selected.extend(additions.plantings)
        used_ids.update(accepted_ids)
        warnings.extend(additions.warnings)
        rationales.append(response.rationale)

    if _planting_counts(plantings=tuple(selected)) == target_counts:
        return _build_accumulated_result(
            selected=selected,
            warnings=warnings,
            rationales=rationales,
            attempts=MAX_LAYOUT_ATTEMPTS,
        )
    completed, added_counts = _fill_remaining_plantings(
        candidates=candidates,
        selected=selected,
        target_counts=target_counts,
        parameters=parameters,
    )
    actual_counts = _planting_counts(plantings=tuple(completed))
    if actual_counts != target_counts:
        raise AgentExecutionError(
            'Не удалось разместить целевое количество растений: в допустимых зонах недостаточно точек '
            'с учётом межпосадочных интервалов'
        )
    fallback_warning = (
        'Python добавил недостающие посадки после попыток LLM: '
        f'trees={added_counts[PlantingType.TREE]}, bushes={added_counts[PlantingType.BUSH]}'
    )
    return LlmLayoutResult(
        plantings=tuple(completed),
        warnings=(*warnings, fallback_warning),
        rationale=_combined_rationale(rationales),
    )


def _validate_additions(
    response: LlmLayoutResponse,
    candidate_index: dict[int, LayoutCandidate],
    selected: list[GeneratedPlanting],
    used_ids: set[int],
    remaining_counts: dict[PlantingType, int],
    parameters: GenerationParametersSchema,
) -> tuple[LlmLayoutResult, set[int]]:
    additions: list[GeneratedPlanting] = []
    accepted_ids: set[int] = set()
    combined = list(selected)
    rejected = 0
    counts = {PlantingType.TREE: 0, PlantingType.BUSH: 0}
    for choice in response.placements:
        candidate = candidate_index.get(choice.candidate_id)
        if (
            candidate is None
            or choice.candidate_id in used_ids | accepted_ids
            or choice.type not in candidate.allowed_types
            or counts[choice.type] >= remaining_counts[choice.type]
            or not _respects_spacing(
                candidate=candidate, planting_type=choice.type, selected=combined, parameters=parameters
            )
        ):
            rejected += 1
            continue
        accepted_ids.add(choice.candidate_id)
        counts[choice.type] += 1
        planting = GeneratedPlanting(type=choice.type, x_m=candidate.x_m, y_m=candidate.y_m)
        additions.append(planting)
        combined.append(planting)

    warnings = []
    if rejected:
        warnings.append(f'Python отклонил некорректные выборы LLM: {rejected}')
    return (
        LlmLayoutResult(plantings=tuple(additions), warnings=tuple(warnings), rationale=response.rationale),
        accepted_ids,
    )


def _target_counts(parameters: GenerationParametersSchema) -> dict[PlantingType, int]:
    target_counts = {
        PlantingType.TREE: parameters.max_trees,
        PlantingType.BUSH: parameters.max_bushes,
    }
    if sum(target_counts.values()) > MAX_LLM_PLANTINGS:
        raise AgentExecutionError(f'Целевое количество растений превышает лимит LLM-планировщика {MAX_LLM_PLANTINGS}')
    return target_counts


def _planting_counts(plantings: tuple[GeneratedPlanting, ...]) -> dict[PlantingType, int]:
    return {
        planting_type: sum(planting.type is planting_type for planting in plantings) for planting_type in PlantingType
    }


def _candidate_payload_for_addition(
    candidates: tuple[LayoutCandidate, ...],
    selected: list[GeneratedPlanting],
    used_ids: set[int],
    remaining_counts: dict[PlantingType, int],
    parameters: GenerationParametersSchema,
) -> list[dict[str, object]]:
    payload = []
    for candidate in candidates:
        if candidate.id in used_ids:
            continue
        allowed_types = [
            planting_type
            for planting_type in candidate.allowed_types
            if remaining_counts[planting_type] > 0
            and _respects_spacing(
                candidate=candidate,
                planting_type=planting_type,
                selected=selected,
                parameters=parameters,
            )
        ]
        if not allowed_types:
            continue
        payload.append(
            {
                'id': candidate.id,
                'x': candidate.x_m,
                'y': candidate.y_m,
                'allowed': [planting_type.value for planting_type in allowed_types],
                'roles': list(candidate.design_roles),
                'road_m': candidate.distance_to_road_m,
                'building_m': candidate.distance_to_building_m,
                'boundary_m': round(candidate.distance_to_boundary_m, 3),
            }
        )
    return payload


def _build_addition_prompt(
    candidate_payload: list[dict[str, object]],
    selected: list[GeneratedPlanting],
    used_ids: set[int],
    remaining_counts: dict[PlantingType, int],
    parameters: GenerationParametersSchema,
) -> str:
    fixed_plantings = [{'type': planting.type.value, 'x': planting.x_m, 'y': planting.y_m} for planting in selected]
    return (
        'Дополни уже зафиксированную композицию. Не перестраивай и не возвращай ранее выбранные посадки. '
        'Для линии выбирай точки с одинаковым направлением и близким шагом между соседями. Новая посадка должна '
        'продолжать ряд или компактную группу того же типа; избегай изолированных точек. candidate_id нельзя '
        'повторять, а type обязан входить в allowed.\n'
        f'Добавь ровно: trees={remaining_counts[PlantingType.TREE]}, '
        f'bushes={remaining_counts[PlantingType.BUSH]}. Минимальные интервалы: '
        f'tree_tree={parameters.tree_tree_distance_m} м, bush_bush={parameters.bush_bush_distance_m} м, '
        f'tree_bush={parameters.tree_bush_distance_m} м.\n'
        f'Зафиксированные посадки: {json.dumps(fixed_plantings, ensure_ascii=False, separators=(",", ":"))}.\n'
        f'Уже использованные candidate_id: {json.dumps(sorted(used_ids), separators=(",", ":"))}.\n'
        f'Кандидаты для дополнения: {json.dumps(candidate_payload, ensure_ascii=False, separators=(",", ":"))}'
    )


def _build_accumulated_result(
    selected: list[GeneratedPlanting],
    warnings: list[str],
    rationales: list[str],
    attempts: int,
) -> LlmLayoutResult:
    result_warnings = list(warnings)
    if attempts > 1:
        result_warnings.append(f'LLM последовательно дополнил композицию за {attempts} попытки')
    return LlmLayoutResult(
        plantings=tuple(selected),
        warnings=tuple(result_warnings),
        rationale=_combined_rationale(rationales),
    )


def _combined_rationale(rationales: list[str]) -> str:
    if not rationales:
        return 'Композиция дополнена детерминированным алгоритмом'
    return ' '.join(rationales)[:2000]


def _fill_remaining_plantings(
    candidates: tuple[LayoutCandidate, ...],
    selected: list[GeneratedPlanting],
    target_counts: dict[PlantingType, int],
    parameters: GenerationParametersSchema,
) -> tuple[list[GeneratedPlanting], dict[PlantingType, int]]:
    """Продолжает выбранные LLM ряды и группы до целевого количества."""

    counts = _planting_counts(plantings=tuple(selected))
    added_counts = {PlantingType.TREE: 0, PlantingType.BUSH: 0}
    used_points = {(planting.x_m, planting.y_m) for planting in selected}
    for planting_type in (PlantingType.TREE, PlantingType.BUSH):
        while counts[planting_type] < target_counts[planting_type]:
            available = [
                candidate
                for candidate in candidates
                if planting_type in candidate.allowed_types
                and (candidate.x_m, candidate.y_m) not in used_points
                and _respects_spacing(
                    candidate=candidate,
                    planting_type=planting_type,
                    selected=selected,
                    parameters=parameters,
                )
            ]
            if not available:
                break
            candidate = min(
                available,
                key=lambda item: _fallback_composition_rank(
                    candidate=item,
                    planting_type=planting_type,
                    selected=selected,
                ),
            )
            selected.append(GeneratedPlanting(type=planting_type, x_m=candidate.x_m, y_m=candidate.y_m))
            used_points.add((candidate.x_m, candidate.y_m))
            counts[planting_type] += 1
            added_counts[planting_type] += 1
    return selected, added_counts


def _fallback_composition_rank(
    candidate: LayoutCandidate,
    planting_type: PlantingType,
    selected: list[GeneratedPlanting],
) -> tuple[float, float, float, float]:
    same_type = [planting for planting in selected if planting.type is planting_type]
    nearest_selected = (
        min(math.hypot(candidate.x_m - planting.x_m, candidate.y_m - planting.y_m) for planting in same_type)
        if same_type
        else 0.0
    )
    if planting_type is PlantingType.TREE:
        role_order = ('road_alley', 'building_edge', 'perimeter', 'open_space')
        distances = [
            value for value in (candidate.distance_to_road_m, candidate.distance_to_building_m) if value is not None
        ]
        object_distance = min(distances) if distances else candidate.distance_to_boundary_m
    else:
        role_order = ('building_edge', 'perimeter', 'road_alley', 'open_space')
        object_distance = (
            candidate.distance_to_building_m
            if candidate.distance_to_building_m is not None
            else candidate.distance_to_boundary_m
        )
    role_rank = min(
        (index for index, role in enumerate(role_order) if role in candidate.design_roles),
        default=len(role_order),
    )
    return float(role_rank), nearest_selected, object_distance, candidate.y_m + candidate.x_m / 1_000_000


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
