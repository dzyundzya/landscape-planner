from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.file_artifact import FileArtifactModel
    from app.models.job import JobModel
    from app.models.plan import PlanModel
    from app.models.plan_validation import PlanValidationModel
    from app.models.project import ProjectModel


class ExportModel(BaseModel):
    """Неизменяемый комплект файлов экспортированной ревизии плана."""

    __tablename__ = 'exports'
    __table_args__ = (
        CheckConstraint('plan_revision > 0', name='ck_exports_plan_revision_positive'),
        UniqueConstraint('job_id', name='uq_exports_job_id'),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey('plans.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    plan_revision: Mapped[int] = mapped_column(nullable=False)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey('plan_validations.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey('jobs.id', ondelete='RESTRICT'),
        nullable=False,
    )
    export_version: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='exports')
    plan: Mapped['PlanModel'] = relationship(back_populates='exports')
    validation: Mapped['PlanValidationModel'] = relationship(back_populates='exports')
    job: Mapped['JobModel'] = relationship(back_populates='export')
    artifacts: Mapped[list['FileArtifactModel']] = relationship(back_populates='export', lazy='selectin')
