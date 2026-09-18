from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FileArtifactFormat, FileArtifactKind


class FileArtifactReadSchema(BaseModel):
    """Схема сформированного файла проекта."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int | None, Field(ge=1)]
    job_id: Annotated[int, Field(ge=1)]
    export_id: Annotated[int | None, Field(ge=1)]
    kind: FileArtifactKind
    format: FileArtifactFormat
    download_name: str
    content_type: str
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(min_length=64, max_length=64)]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
