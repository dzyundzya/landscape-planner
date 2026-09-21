from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent import LandscapeAgentRuntime
from app.core.config.settings.base_settings import BackendSettings
from app.repositories.crud.projects import ProjectCRUDRepository
from app.schemas.agent import AgentMessageReadSchema
from app.services.exceptions.projects import ProjectNotFoundError


class AgentService:
    """Прикладной сценарий одного сообщения продуктовому агенту."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: BackendSettings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def send_message(self, project_id: int, message: str) -> AgentMessageReadSchema:
        """Проверяет проект и запускает ограниченного LangChain-агента."""

        async with self.session_factory() as session:
            if await ProjectCRUDRepository(session).get_obj_by_id(obj_id=project_id) is None:
                raise ProjectNotFoundError(project_id=project_id)

        answer, tool_calls = await LandscapeAgentRuntime(
            session_factory=self.session_factory,
            settings=self.settings,
        ).invoke(project_id=project_id, message=message)
        return AgentMessageReadSchema(
            message=answer,
            model=self.settings.LLM_MODEL or '',
            tool_calls=tool_calls,
        )
