from io import StringIO

import ezdxf
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobModel, JobStatus, ProjectModel
from app.schemas.analysis import AnalysisResultSchema
from app.services.analyses import AnalysisService
from app.services.jobs import JobService


def build_dxf() -> bytes:
    """Создаёт минимальный валидный DXF для теста анализа."""

    document = ezdxf.new('R2010')
    document.modelspace().add_line((0, 0), (10, 10), dxfattribs={'layer': 'SITE'})
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode()


async def upload_dxf(client: AsyncClient, project_id: int, name: str = 'site.dxf') -> int:
    """Загружает тестовый DXF и возвращает ID версии исходника."""

    response = await client.post(
        f'/api/projects/{project_id}/files/',
        files={'file': (name, build_dxf(), 'application/dxf')},
    )
    assert response.status_code == 201
    return response.json()['id']


def analysis_result() -> AnalysisResultSchema:
    """Возвращает структурированный результат тестового анализа."""

    return AnalysisResultSchema(
        dxf_version='AC1024',
        drawing_units='m',
        entity_counts={'LINE': 1},
        layers=[{'name': 'SITE', 'entity_count': 1, 'entity_counts': {'LINE': 1}}],
        bounds={'min_x': 0, 'min_y': 0, 'max_x': 10, 'max_y': 10},
        requires_user_confirmation=True,
    )


async def publish_current_analysis(
    client: AsyncClient,
    db_session: AsyncSession,
    project_id: int,
) -> tuple[int, int]:
    """Загружает исходник, запускает и публикует его анализ."""

    project_file_id = await upload_dxf(client=client, project_id=project_id)
    response = await client.post(f'/api/projects/{project_id}/analyze')
    job_id = response.json()['id']
    claimed_job = await JobService(async_session=db_session).claim_next_job()
    assert claimed_job is not None
    assert claimed_job.id == job_id
    analysis = await AnalysisService(async_session=db_session).publish_analysis(
        project_id=project_id,
        project_file_id=project_file_id,
        job_id=job_id,
        result=analysis_result(),
    )
    return analysis.id, job_id


async def test_enqueue_analysis(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет постановку анализа текущего DXF в очередь без дубликатов."""

    project_file_id = await upload_dxf(client=client, project_id=project.id)

    first_response = await client.post(f'/api/projects/{project.id}/analyze')
    second_response = await client.post(f'/api/projects/{project.id}/analyze')
    job_data = first_response.json()

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert second_response.json()['id'] == job_data['id']
    assert job_data['project_id'] == project.id
    assert job_data['project_file_id'] == project_file_id
    assert job_data['type'] == 'analyze'
    assert job_data['status'] == 'queued'

    job = await db_session.scalar(select(JobModel).where(JobModel.id == job_data['id']))
    assert job is not None
    assert job.input_data['project_file_id'] == project_file_id
    assert job.input_data['analysis_schema_version'] == 5


async def test_enqueue_analysis_requires_source(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет запрет анализа проекта без исходного файла."""

    response = await client.post(f'/api/projects/{project.id}/analyze')

    assert response.status_code == 409
    assert response.json() == {'detail': f'У проекта с id={project.id} отсутствует исходный файл'}


async def test_enqueue_analysis_rejects_dwf(client: AsyncClient, project: ProjectModel) -> None:
    """Проверяет запрет передачи DWF напрямую в DXF-анализатор."""

    upload_response = await client.post(
        f'/api/projects/{project.id}/files/',
        files={'file': ('site.dwf', b'(DWF V06.00)\n', 'model/vnd.dwf')},
    )
    assert upload_response.status_code == 201

    response = await client.post(f'/api/projects/{project.id}/analyze')

    assert response.status_code == 409
    assert response.json() == {'detail': 'Текущий исходник проекта должен быть готовым DXF-файлом'}


async def test_get_current_analysis(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет получение опубликованного анализа текущей версии исходника."""

    analysis_id, job_id = await publish_current_analysis(client, db_session, project.id)

    response = await client.get(f'/api/projects/{project.id}/analysis')
    data = response.json()

    assert response.status_code == 200
    assert data['id'] == analysis_id
    assert data['job_id'] == job_id
    assert data['schema_version'] == 5
    assert data['result'] == analysis_result().model_dump(mode='json')


async def test_new_source_invalidates_current_analysis(
    client: AsyncClient,
    db_session: AsyncSession,
    project: ProjectModel,
) -> None:
    """Проверяет, что анализ старой версии не выдаётся для нового исходника."""

    _, job_id = await publish_current_analysis(client, db_session, project.id)
    job = await db_session.get(JobModel, job_id)
    assert job is not None
    assert job.status is JobStatus.SUCCEEDED
    await upload_dxf(client=client, project_id=project.id, name='new-site.dxf')

    response = await client.get(f'/api/projects/{project.id}/analysis')

    assert response.status_code == 404
    assert response.json() == {'detail': f'Объект «анализ проекта» с id={project.id} не найден'}
