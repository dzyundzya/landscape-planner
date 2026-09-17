from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.config_snapshot import ConfigSnapshotModel
    from app.models.job import JobModel
    from app.models.plan import PlanModel
    from app.models.project import ProjectModel
    from app.models.project_file import ProjectFileModel


class AnalysisModel(BaseModel):
    """Неизменяемый результат анализа исходного DXF."""

    __tablename__ = 'analyses'
    __table_args__ = (
        CheckConstraint('schema_version > 0', name='ck_analyses_schema_version_positive'),
        UniqueConstraint('job_id', name='uq_analyses_job_id'),
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
    job_id: Mapped[int] = mapped_column(
        ForeignKey('jobs.id', ondelete='RESTRICT'),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='analyses')
    project_file: Mapped['ProjectFileModel'] = relationship(back_populates='analyses')
    job: Mapped['JobModel'] = relationship(back_populates='analysis')
    config_snapshots: Mapped[list['ConfigSnapshotModel']] = relationship(back_populates='analysis')
    plans: Mapped[list['PlanModel']] = relationship(back_populates='analysis')
