from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import PlanStatus

if TYPE_CHECKING:
    from app.models.analysis import AnalysisModel
    from app.models.config_snapshot import ConfigSnapshotModel
    from app.models.export import ExportModel
    from app.models.job import JobModel
    from app.models.plan_validation import PlanValidationModel
    from app.models.planting import PlantingModel
    from app.models.project import ProjectModel
    from app.models.project_file import ProjectFileModel


class PlanModel(BaseModel):
    """Версионируемый план озеленения для фиксированных входов."""

    __tablename__ = 'plans'
    __table_args__ = (
        CheckConstraint('revision > 0', name='ck_plans_revision_positive'),
        UniqueConstraint('job_id', name='uq_plans_job_id'),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    project_file_id: Mapped[int] = mapped_column(
        ForeignKey('project_files.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey('analyses.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    config_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey('config_snapshots.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey('jobs.id', ondelete='RESTRICT'),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(
            PlanStatus,
            name='plan_status',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='plans')
    project_file: Mapped['ProjectFileModel'] = relationship(back_populates='plans')
    analysis: Mapped['AnalysisModel'] = relationship(back_populates='plans')
    config_snapshot: Mapped['ConfigSnapshotModel'] = relationship(back_populates='plans')
    job: Mapped['JobModel'] = relationship(back_populates='plan')
    plantings: Mapped[list['PlantingModel']] = relationship(
        back_populates='plan',
        cascade='all, delete-orphan',
        passive_deletes=True,
        lazy='selectin',
    )
    validations: Mapped[list['PlanValidationModel']] = relationship(
        back_populates='plan',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    exports: Mapped[list['ExportModel']] = relationship(
        back_populates='plan',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
