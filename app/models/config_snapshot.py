from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import CoordinateUnit, NormativeRulesStatus

if TYPE_CHECKING:
    from app.models.analysis import AnalysisModel
    from app.models.plan import PlanModel
    from app.models.project import ProjectModel


class ConfigSnapshotModel(BaseModel):
    """Неизменяемый снимок подтверждённых настроек проекта."""

    __tablename__ = 'config_snapshots'
    __table_args__ = (
        CheckConstraint('version > 0', name='ck_config_snapshots_version_positive'),
        CheckConstraint('schema_version > 0', name='ck_config_snapshots_schema_version_positive'),
        CheckConstraint('unit_scale_to_meters > 0', name='ck_config_snapshots_unit_scale_positive'),
        UniqueConstraint('project_id', 'version', name='uq_config_snapshots_project_version'),
        UniqueConstraint('project_id', 'content_sha256', name='uq_config_snapshots_project_content'),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey('analyses.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False)
    coordinate_unit: Mapped[CoordinateUnit] = mapped_column(
        Enum(
            CoordinateUnit,
            name='coordinate_unit',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    unit_scale_to_meters: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    boundary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    layer_mappings: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    generation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rules_status: Mapped[NormativeRulesStatus] = mapped_column(
        Enum(
            NormativeRulesStatus,
            name='normative_rules_status',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    rules_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rules_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='config_snapshots')
    analysis: Mapped['AnalysisModel'] = relationship(back_populates='config_snapshots')
    plans: Mapped[list['PlanModel']] = relationship(back_populates='config_snapshot')
