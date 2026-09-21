from typing import Annotated

from fastapi import Depends

from app.core.config.manager import settings
from app.core.db.database import async_db
from app.services.agents import AgentService


def get_agent_service() -> AgentService:
    """Создаёт сервис продуктового агента."""

    return AgentService(session_factory=async_db.async_session_maker, settings=settings)


AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]
