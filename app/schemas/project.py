from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base.pagination import PageResponseSchema


class ProjectCreateSchema(BaseModel):
    """Схема создания проекта."""

    name: Annotated[
        str, Field(min_length=2, max_length=255, description='Название проекта.')
    ]
    description: Annotated[
        str | None, Field(max_length=2000, description='Описание проекта')
    ] = None

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra='forbid'
    )


class ProjectReadSchema(BaseModel):
    """Схема проекта для ответа."""

    id: Annotated[int, Field(ge=1)]
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )


class ProjectPageSchema(PageResponseSchema[ProjectReadSchema]):
    """Схема списка проектов с пагинацией."""

    pass
