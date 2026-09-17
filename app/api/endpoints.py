from fastapi import APIRouter

from app.api.routers.jobs import router as job_router
from app.api.routers.project_files import router as project_file_router
from app.api.routers.projects import router as project_router

router = APIRouter()

router.include_router(job_router)
router.include_router(project_router)
router.include_router(project_file_router)
