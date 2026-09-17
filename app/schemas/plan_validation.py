from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import NormativeRulesStatus, ValidationStatus

NonNegativeInt = Annotated[int, Field(ge=0)]


class CheckResultSchema(BaseModel):
    """Проверяемый факт Validator с трассировкой до источника и правила."""

    check_type: Annotated[str, Field(min_length=1, max_length=100)]
    status: ValidationStatus
    planting_id: UUID | None = None
    actual: Decimal | None = None
    required: Decimal | None = None
    unit: Annotated[str | None, Field(min_length=1, max_length=32)] = None
    rule_id: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    rule_version: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    source_object_id: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    document: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    clause: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    reason: Annotated[str, Field(min_length=1, max_length=2000)]

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

    @model_validator(mode='after')
    def validate_measurement(self) -> 'CheckResultSchema':
        """Не допускает частично заполненное измерение расстояния."""

        measurement = (self.actual, self.required, self.unit)
        if any(value is not None for value in measurement) and not all(value is not None for value in measurement):
            raise ValueError('actual, required and unit must be provided together')
        return self


class PlanValidationPublishSchema(BaseModel):
    """Результаты независимого Validator для публикации сервисом."""

    validator_version: Annotated[str, Field(min_length=1, max_length=100)]
    checks: Annotated[list[CheckResultSchema], Field(min_length=1)]

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ValidationSummarySchema(BaseModel):
    """Количество проверок по каждому итоговому статусу."""

    total: NonNegativeInt
    passed: NonNegativeInt
    failed: NonNegativeInt
    needs_verification: NonNegativeInt

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_total(self) -> 'ValidationSummarySchema':
        """Проверяет согласованность общего количества проверок."""

        if self.passed + self.failed + self.needs_verification != self.total:
            raise ValueError('Validation summary counts must equal total')
        return self


class PlanValidationReadSchema(BaseModel):
    """Сохранённый результат проверки ревизии плана."""

    id: Annotated[int, Field(ge=1)]
    plan_id: Annotated[int, Field(ge=1)]
    plan_revision: Annotated[int, Field(ge=1)]
    status: ValidationStatus
    validator_version: str
    checks: list[CheckResultSchema]
    summary: ValidationSummarySchema
    rules_status: NormativeRulesStatus
    rules_version: str | None
    rules_sha256: Annotated[str | None, Field(min_length=64, max_length=64)]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
