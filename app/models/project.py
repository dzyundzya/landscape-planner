from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.analysis import AnalysisModel
    from app.models.config_snapshot import ConfigSnapshotModel
    from app.models.file_artifact import FileArtifactModel
    from app.models.job import JobModel
    from app.models.plan import PlanModel
    from app.models.project_file import ProjectFileModel


class ProjectModel(BaseModel):
    """Проект озеленения."""

    __tablename__ = 'projects'

    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    files: Mapped[list['ProjectFileModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    jobs: Mapped[list['JobModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    artifacts: Mapped[list['FileArtifactModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    analyses: Mapped[list['AnalysisModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    config_snapshots: Mapped[list['ConfigSnapshotModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    plans: Mapped[list['PlanModel']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
