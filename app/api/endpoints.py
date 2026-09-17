from fastapi import APIRouter

from app.api.routers.projects import router as project_router

router = APIRouter()

router.include_router(project_router)
