from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.dependencies.file_artifacts import FileArtifactServiceDep

router = APIRouter(prefix='/projects/{project_id}/artifacts', tags=['File artifacts'])


@router.get('/{artifact_id}', response_class=FileResponse)
async def download_file_artifact(
    project_id: int,
    artifact_id: int,
    service: FileArtifactServiceDep,
) -> FileResponse:
    """Скачивает сформированный файл проекта."""

    download = await service.get_download(project_id=project_id, artifact_id=artifact_id)
    return FileResponse(
        path=download.path,
        filename=download.download_name,
        media_type=download.content_type,
    )
