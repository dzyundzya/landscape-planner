from io import StringIO
from pathlib import Path

import ezdxf
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectFileModel, ProjectModel


def build_dxf() -> bytes:
    """Создаёт минимальный валидный DXF для теста."""

    document = ezdxf.new('R2010')
    document.modelspace().add_line((0, 0), (10, 10))
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode()


async def test_upload_dxf(
    client: AsyncClient,
    project: ProjectModel,
    db_session: AsyncSession,
    file_storage_root: Path,
) -> None:
    """Проверяет сохранение и регистрацию валидного DXF."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('../../site.dxf', build_dxf(), 'application/dxf')},
    )
    response_data = response.json()

    assert response.status_code == 201
    assert response_data['project_id'] == project.id
    assert response_data['version'] == 1
    assert response_data['format'] == 'dxf'
    assert response_data['status'] == 'ready'
    assert response_data['original_name'] == 'site.dxf'
    assert response_data['size_bytes'] > 0
    assert len(response_data['sha256']) == 64
    assert 'storage_key' not in response_data

    project_file = await db_session.scalar(select(ProjectFileModel).where(ProjectFileModel.id == response_data['id']))
    assert project_file is not None
    assert (file_storage_root / project_file.storage_key).is_file()


async def test_upload_dwf_requires_conversion(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет приём DWF без ложного статуса готовности к анализу."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('site.dwf', b'(DWF V06.00)\n', 'model/vnd.dwf')},
    )

    assert response.status_code == 201
    assert response.json()['format'] == 'dwf'
    assert response.json()['status'] == 'conversion_required'


async def test_upload_creates_new_version(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет создание новой версии при повторной загрузке."""

    first_response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('first.dxf', build_dxf(), 'application/dxf')},
    )
    second_response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('second.dxf', build_dxf(), 'application/dxf')},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()['version'] == 1
    assert second_response.json()['version'] == 2


async def test_upload_rejects_unsupported_format(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет отклонение файла с неподдерживаемым расширением."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('site.pdf', b'%PDF', 'application/pdf')},
    )

    assert response.status_code == 422
    assert response.json() == {'detail': 'Only DXF and DWF files are supported'}


async def test_upload_rejects_invalid_dxf(
    client: AsyncClient,
    project: ProjectModel,
    file_storage_root: Path,
) -> None:
    """Проверяет отклонение повреждённого DXF и удаление файла."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('broken.dxf', b'not a dxf', 'application/dxf')},
    )

    assert response.status_code == 422
    assert response.json() == {'detail': 'Uploaded DXF file is invalid'}
    assert not list(file_storage_root.rglob('*.dxf'))


async def test_upload_rejects_invalid_dwf(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет отклонение файла без обязательной сигнатуры DWF."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('broken.dwf', b'not a dwf', 'model/vnd.dwf')},
    )

    assert response.status_code == 422
    assert response.json() == {'detail': 'Uploaded DWF file is invalid'}


async def test_upload_rejects_empty_file(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет отклонение пустого исходного файла."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('empty.dwf', b'', 'model/vnd.dwf')},
    )

    assert response.status_code == 422
    assert response.json() == {'detail': 'Uploaded file is empty'}


async def test_upload_rejects_file_above_limit(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет ответ 413 при превышении лимита размера."""

    response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('large.dwf', b'x' * (1024 * 1024 + 1), 'model/vnd.dwf')},
    )

    assert response.status_code == 413
    assert response.json() == {'detail': 'File size exceeds 1048576 bytes'}


async def test_upload_returns_404_for_missing_project(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет запрет загрузки для отсутствующего проекта."""

    missing_project_id = project.id + 1000
    response = await client.post(
        f'/api/projects/{missing_project_id}/files/',
        files={'file': ('site.dxf', build_dxf(), 'application/dxf')},
    )

    assert response.status_code == 404
    assert response.json() == {'detail': f'Project with id={missing_project_id} not found'}
