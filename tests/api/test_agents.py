from httpx import AsyncClient

from app.models import ProjectModel


async def test_agent_reports_disabled_configuration(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет понятный ответ API, когда подключение LangChain-агента отключено."""

    response = await client.post(
        f'/api/projects/{project.id}/agent/messages',
        json={'message': 'Что сейчас происходит с проектом?'},
    )

    assert response.status_code == 503
    assert response.json() == {'detail': 'Агент отключён. Установите AGENT_ENABLED=true'}


async def test_agent_hides_missing_project_before_model_call(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет привязку агента к существующему проекту из адреса запроса."""

    response = await client.post(
        f'/api/projects/{project.id + 1000}/agent/messages',
        json={'message': 'Покажи состояние проекта'},
    )

    assert response.status_code == 404
    assert response.json() == {'detail': f'Объект «проект» с id={project.id + 1000} не найден'}
