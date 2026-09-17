from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import PlantingSource, PlantingType

if TYPE_CHECKING:
    from app.models.plan import PlanModel


class PlantingModel(BaseModel):
    """Дерево или кустарник в локальных координатах плана."""

    __tablename__ = 'plantings'
    __table_args__ = (Index('ix_plantings_plan_type', 'plan_id', 'type'),)

    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        default=uuid4,
        unique=True,
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey('plans.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    type: Mapped[PlantingType] = mapped_column(
        Enum(
            PlantingType,
            name='planting_type',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    source: Mapped[PlantingSource] = mapped_column(
        Enum(
            PlantingSource,
            name='planting_source',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    x_m: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    y_m: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    species: Mapped[str | None] = mapped_column(String(255), nullable=True)

    plan: Mapped['PlanModel'] = relationship(back_populates='plantings')
