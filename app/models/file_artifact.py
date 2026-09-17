from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import FileArtifactFormat, FileArtifactKind

if TYPE_CHECKING:
    from app.models.job import JobModel
    from app.models.project import ProjectModel
    from app.models.project_file import ProjectFileModel


class FileArtifactModel(BaseModel):
    """Неизменяемый файл, сформированный фоновой задачей."""

    __tablename__ = 'file_artifacts'
    __table_args__ = (
        CheckConstraint('size_bytes > 0', name='ck_file_artifacts_size_bytes_positive'),
        UniqueConstraint('job_id', 'kind', name='uq_file_artifacts_job_kind'),
    )

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
    job_id: Mapped[int] = mapped_column(
        ForeignKey('jobs.id', ondelete='RESTRICT'),
        index=True,
        nullable=False,
    )
    kind: Mapped[FileArtifactKind] = mapped_column(
        Enum(
            FileArtifactKind,
            name='file_artifact_kind',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    format: Mapped[FileArtifactFormat] = mapped_column(
        Enum(
            FileArtifactFormat,
            name='file_artifact_format',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    download_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='artifacts')
    project_file: Mapped['ProjectFileModel | None'] = relationship(back_populates='artifacts')
    job: Mapped['JobModel'] = relationship(back_populates='artifacts')
