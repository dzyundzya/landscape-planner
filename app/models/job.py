from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import JobStatus, JobType

if TYPE_CHECKING:
    from app.models.analysis import AnalysisModel
    from app.models.export import ExportModel
    from app.models.file_artifact import FileArtifactModel
    from app.models.plan import PlanModel
    from app.models.project import ProjectModel
    from app.models.project_file import ProjectFileModel


class JobModel(BaseModel):
    """Фоновая задача проекта."""

    __tablename__ = 'jobs'
    __table_args__ = (Index('ix_jobs_queue', 'status', 'created_at', 'id'),)

    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    project_file_id: Mapped[int | None] = mapped_column(
        ForeignKey('project_files.id', ondelete='SET NULL'),
        index=True,
        nullable=True,
    )
    type: Mapped[JobType] = mapped_column(
        Enum(
            JobType,
            name='job_type',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name='job_status',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped['ProjectModel'] = relationship(back_populates='jobs')
    project_file: Mapped['ProjectFileModel | None'] = relationship(back_populates='jobs')
    artifacts: Mapped[list['FileArtifactModel']] = relationship(back_populates='job')
    analysis: Mapped['AnalysisModel | None'] = relationship(back_populates='job')
    plan: Mapped['PlanModel | None'] = relationship(back_populates='job')
    export: Mapped['ExportModel | None'] = relationship(back_populates='job')
