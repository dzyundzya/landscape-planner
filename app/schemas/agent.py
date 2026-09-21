from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AgentMessageCreateSchema(BaseModel):
    """Запрос пользователя к агенту текущего проекта."""

    message: Annotated[str, Field(min_length=1, max_length=4000)]

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class AgentMessageReadSchema(BaseModel):
    """Ответ агента и фактически вызванные инструменты."""

    message: str
    model: str
    tool_calls: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')
