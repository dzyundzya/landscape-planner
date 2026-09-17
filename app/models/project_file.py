from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import ProjectFileFormat, ProjectFileStatus

if TYPE_CHECKING:
    from app.models.project import ProjectModel


class ProjectFileModel(BaseModel):
    """Исходный файл проекта."""

    __tablename__ = 'project_files'
    __table_args__ = (
        CheckConstraint('size_bytes > 0', name='ck_project_files_size_bytes_positive'),
        UniqueConstraint('project_id', 'version', name='uq_project_files_project_version'),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    format: Mapped[ProjectFileFormat] = mapped_column(
        Enum(
            ProjectFileFormat,
            name='project_file_format',
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[ProjectFileStatus] = mapped_column(
        Enum(
            ProjectFileStatus,
            name='project_file_status',
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped['ProjectModel'] = relationship(back_populates='files')
