from datetime import datetime

from httpx import AsyncClient

from app.models import ProjectModel


async def test_get_project_by_id(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет получение проекта по ID."""

    response = await client.get(f'/api/projects/{project.id}')
    response_data = response.json()
    created_at = response_data.pop('created_at')

    assert response.status_code == 200
    assert response_data == {
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'updated_at': None,
    }
    assert datetime.fromisoformat(created_at) == project.created_at


async def test_get_missing_project_returns_404(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет ответ 404 при запросе отсутствующего проекта."""

    missing_project_id = project.id + 1000
    response = await client.get(f'/api/projects/{missing_project_id}')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Объект «проект» с id={missing_project_id} не найден'}


async def test_get_projects_returns_page(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет получение страницы проектов с метаданными пагинации."""

    response = await client.get('/api/projects/?page=1&limit=20')
    page = response.json()

    assert response.status_code == 200
    assert page['total'] == 1
    assert page['page'] == 1
    assert page['limit'] == 20
    assert page['pages'] == 1
    assert [item['id'] for item in page['items']] == [project.id]


async def test_create_project(client: AsyncClient) -> None:
    """Проверяет создание проекта и заполнение серверных полей."""

    data = {
        'name': 'Новый участок',
        'description': 'Проверка создания проекта',
    }

    response = await client.post('/api/projects/', json=data)
    project = response.json()

    assert response.status_code == 201
    assert project['id'] > 0
    assert project['name'] == data['name']
    assert project['description'] == data['description']
    assert project['created_at'] is not None
    assert project['updated_at'] is None


async def test_get_projects_rejects_invalid_pagination(client: AsyncClient) -> None:
    """Проверяет отклонение недопустимых параметров пагинации."""

    response = await client.get('/api/projects/?page=0&limit=101')

    assert response.status_code == 422
