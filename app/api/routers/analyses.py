from fastapi import APIRouter, status

from app.api.dependencies.analyses import AnalysisServiceDep
from app.schemas.analysis import AnalysisReadSchema
from app.schemas.job import JobReadSchema

router = APIRouter(prefix='/projects/{project_id}', tags=['Analyses'])


@router.post('/analyze', response_model=JobReadSchema, status_code=status.HTTP_202_ACCEPTED)
async def analyze_project(project_id: int, service: AnalysisServiceDep):
    """Ставит анализ текущего исходника проекта в очередь."""

    return await service.enqueue_analysis(project_id=project_id)


@router.get('/analysis', response_model=AnalysisReadSchema)
async def get_project_analysis(project_id: int, service: AnalysisServiceDep):
    """Возвращает анализ текущей версии исходника проекта."""

    return await service.get_current_analysis(project_id=project_id)
