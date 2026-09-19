from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies.project_files import ProjectFileServiceDep
from app.schemas.project_file import ProjectFileReadSchema

router = APIRouter(prefix='/projects/{project_id}/files', tags=['Исходные файлы'])


@router.post('/', response_model=ProjectFileReadSchema, status_code=status.HTTP_201_CREATED)
async def upload_project_file(
    project_id: int,
    service: ProjectFileServiceDep,
    file: Annotated[UploadFile, File(description='Исходный файл DXF или DWF')],
):
    """Загружает новую версию исходного файла проекта."""

    return await service.upload_source_file(
        project_id=project_id,
        original_name=file.filename or '',
        content_type=file.content_type,
        source=file.file,
    )
