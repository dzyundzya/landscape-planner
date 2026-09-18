from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import PlantingSource, PlantingType


class PlantingCreateSchema(BaseModel):
    """Схема новой посадки в локальных метрах."""

    type: PlantingType
    x_m: float
    y_m: float
    species: Annotated[str | None, Field(min_length=1, max_length=255)] = None

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class PlantingPatchSchema(BaseModel):
    """Схема перемещения или изменения типа посадки."""

    type: PlantingType | None = None
    x_m: float | None = None
    y_m: float | None = None
    species: Annotated[str | None, Field(min_length=1, max_length=255)] = None

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

    @model_validator(mode='after')
    def validate_patch(self) -> 'PlantingPatchSchema':
        """Требует хотя бы одно поле и запрещает null для обязательных полей."""

        if not self.model_fields_set:
            raise ValueError('Изменение посадки должно содержать хотя бы одно поле')
        for field_name in ('type', 'x_m', 'y_m'):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f'Поле {field_name} не может быть null')
        return self


class PlantingReadSchema(BaseModel):
    """Схема посадки плана."""

    public_id: UUID
    plan_id: Annotated[int, Field(ge=1)]
    type: PlantingType
    source: PlantingSource
    x_m: Decimal
    y_m: Decimal
    species: str | None

    model_config = ConfigDict(from_attributes=True)


class PlantingMutationReadSchema(BaseModel):
    """Результат изменения посадки и новая ревизия плана."""

    plan_revision: Annotated[int, Field(ge=1)]
    planting: PlantingReadSchema
