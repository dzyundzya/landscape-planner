from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectFileFormat, ProjectFileStatus


class ProjectFileReadSchema(BaseModel):
    """Схема исходного файла проекта."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    version: Annotated[int, Field(ge=1)]
    format: ProjectFileFormat
    status: ProjectFileStatus
    original_name: str
    content_type: str | None
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(min_length=64, max_length=64)]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
