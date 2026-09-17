from io import BytesIO, StringIO

import ezdxf
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, JobType, ProjectModel
from app.schemas.analysis import AnalysisBoundsSchema, AnalysisResultSchema
from app.services.analyses import AnalysisService
from app.services.exceptions.analyses import InvalidAnalysisError
from app.services.jobs import JobService
from app.services.project_files import ProjectFileService
from app.storage import LocalFileStorage


def build_dxf() -> bytes:
    """Создаёт валидный DXF для сервисных тестов."""

    document = ezdxf.new('R2010')
    document.modelspace().add_circle((5, 5), radius=2)
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode()


async def create_source_file(
    db_session: AsyncSession,
    project_id: int,
    storage_root,
):
    """Создаёт готовый исходный DXF через прикладной сервис."""

    return await ProjectFileService(
        async_session=db_session,
        storage=LocalFileStorage(root=storage_root, max_size_bytes=1024 * 1024),
    ).upload_source_file(
        project_id=project_id,
        original_name='site.dxf',
        content_type='application/dxf',
        source=BytesIO(build_dxf()),
    )


def result_schema() -> AnalysisResultSchema:
    """Создаёт минимальный результат анализа."""

    return AnalysisResultSchema(entity_counts={'CIRCLE': 1})


async def test_publish_analysis_completes_job_atomically(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root,
) -> None:
    """Проверяет публикацию результата вместе с успешным завершением задачи."""

    project_file = await create_source_file(db_session, project.id, file_storage_root)
    analysis_service = AnalysisService(async_session=db_session)
    job = await analysis_service.enqueue_analysis(project_id=project.id)
    claimed_job = await JobService(async_session=db_session).claim_next_job()
    assert claimed_job is not None
    assert claimed_job.id == job.id

    analysis = await analysis_service.publish_analysis(
        project_id=project.id,
        project_file_id=project_file.id,
        job_id=job.id,
        result=result_schema(),
    )

    assert analysis.result == result_schema().model_dump(mode='json')
    assert job.status is JobStatus.SUCCEEDED
    assert job.result == {'analysis_id': analysis.id}
    assert job.finished_at is not None

    repeated_analysis = await analysis_service.publish_analysis(
        project_id=project.id,
        project_file_id=project_file.id,
        job_id=job.id,
        result=result_schema(),
    )
    assert repeated_analysis.id == analysis.id


async def test_publish_analysis_rejects_wrong_job_type(
    db_session: AsyncSession,
    project: ProjectModel,
    file_storage_root,
) -> None:
    """Проверяет запрет публикации анализа из задачи другого типа."""

    project_file = await create_source_file(db_session, project.id, file_storage_root)
    job_service = JobService(async_session=db_session)
    job = await job_service.enqueue_job(
        project_id=project.id,
        project_file_id=project_file.id,
        job_type=JobType.EXPORT,
        input_data={},
    )
    await job_service.claim_next_job()

    with pytest.raises(InvalidAnalysisError):
        await AnalysisService(async_session=db_session).publish_analysis(
            project_id=project.id,
            project_file_id=project_file.id,
            job_id=job.id,
            result=result_schema(),
        )


@pytest.mark.parametrize(
    'bounds',
    [
        {'min_x': 2, 'min_y': 0, 'max_x': 1, 'max_y': 1},
        {'min_x': 0, 'min_y': float('nan'), 'max_x': 1, 'max_y': 1},
    ],
)
def test_analysis_bounds_reject_invalid_coordinates(bounds: dict[str, float]) -> None:
    """Проверяет отклонение перепутанных и нечисловых границ анализа."""

    with pytest.raises(ValidationError):
        AnalysisBoundsSchema.model_validate(bounds)
