from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import NormativeRulesStatus, ValidationStatus

if TYPE_CHECKING:
    from app.models.plan import PlanModel


class PlanValidationModel(BaseModel):
    """Неизменяемый результат Validator для конкретной ревизии плана."""

    __tablename__ = 'plan_validations'
    __table_args__ = (
        CheckConstraint('plan_revision > 0', name='ck_plan_validations_revision_positive'),
        UniqueConstraint('plan_id', 'plan_revision', name='uq_plan_validations_plan_revision'),
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey('plans.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    plan_revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[ValidationStatus] = mapped_column(
        Enum(
            ValidationStatus,
            name='validation_status',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    validator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    rules_status: Mapped[NormativeRulesStatus] = mapped_column(
        Enum(
            NormativeRulesStatus,
            name='validation_rules_status',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    rules_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rules_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    plan: Mapped['PlanModel'] = relationship(back_populates='validations')
