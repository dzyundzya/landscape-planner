from fastapi import APIRouter

from app.api.dependencies.agents import AgentServiceDep
from app.schemas.agent import AgentMessageCreateSchema, AgentMessageReadSchema

router = APIRouter(prefix='/projects/{project_id}/agent/messages', tags=['Agent'])


@router.post('', response_model=AgentMessageReadSchema)
async def send_agent_message(
    project_id: int,
    payload: AgentMessageCreateSchema,
    service: AgentServiceDep,
) -> AgentMessageReadSchema:
    """Передаёт сообщение агенту, привязанному к проекту из URL."""

    return await service.send_message(project_id=project_id, message=payload.message)
