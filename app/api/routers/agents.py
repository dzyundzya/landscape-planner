from fastapi import APIRouter, status

from app.api.dependencies.agents import AgentServiceDep
from app.schemas.agent import AgentMessageCreateSchema, AgentMessageReadSchema
from app.schemas.job import JobReadSchema

router = APIRouter(prefix='/projects/{project_id}/agent', tags=['Agent'])


@router.post('/messages', response_model=AgentMessageReadSchema)
async def send_agent_message(
    project_id: int,
    payload: AgentMessageCreateSchema,
    service: AgentServiceDep,
) -> AgentMessageReadSchema:
    """Передаёт сообщение агенту, привязанному к проекту из URL."""

    return await service.send_message(project_id=project_id, message=payload.message)


@router.post('/autoplan', response_model=JobReadSchema, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_autoplan(project_id: int, service: AgentServiceDep) -> JobReadSchema:
    """Запускает автоматическую расстановку по подтверждённым настройкам проекта."""

    return await service.start_autoplan(project_id=project_id)
