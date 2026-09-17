from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models.enums import JobStatus, JobType


class JobReadSchema(BaseModel):
    """Схема состояния фоновой задачи."""

    id: Annotated[int, Field(ge=1)]
    project_id: Annotated[int, Field(ge=1)]
    project_file_id: Annotated[int | None, Field(ge=1)]
    type: JobType
    status: JobStatus
    stage: str | None
    result: dict[str, JsonValue] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
