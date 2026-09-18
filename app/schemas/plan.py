from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import PlanStatus
from app.schemas.planting import PlantingReadSchema

NonNegativeInt = Annotated[int, Field(ge=0)]


class PlanGenerationSummarySchema(BaseModel):
    """Проверяемая сводка результата генератора."""

    candidate_count: NonNegativeInt
    tree_count: NonNegativeInt
    bush_count: NonNegativeInt
    rejected_candidate_count: NonNegativeInt
    strategy: Annotated[str, Field(min_length=1, max_length=100)] = 'hex_grid_greedy'
    selected_offset_index: NonNegativeInt = 0
    offset_x_m: float = 0.0
    offset_y_m: float = 0.0
    grid_spacing_m: Annotated[float | None, Field(gt=0)] = None
    warnings: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_counts(self) -> 'PlanGenerationSummarySchema':
        """Проверяет согласованность количества кандидатов и посадок."""

        if self.tree_count + self.bush_count + self.rejected_candidate_count > self.candidate_count:
            raise ValueError('Сумма выбранных и отклонённых кандидатов не должна превышать их общее количество')
        return self


class PlanReadSchema(BaseModel):
    """Схема плана озеленения."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int, Field(ge=1)]
    analysis_id: Annotated[int, Field(ge=1)]
    config_snapshot_id: Annotated[int, Field(ge=1)]
    job_id: Annotated[int, Field(ge=1)]
    revision: Annotated[int, Field(ge=1)]
    status: PlanStatus
    generator_version: str
    generation_summary: PlanGenerationSummarySchema
    plantings: list[PlantingReadSchema]
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
