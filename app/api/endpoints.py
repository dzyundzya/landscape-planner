from fastapi import APIRouter

from app.api.routers.analyses import router as analysis_router
from app.api.routers.config_snapshots import router as config_snapshot_router
from app.api.routers.file_artifacts import router as file_artifact_router
from app.api.routers.jobs import router as job_router
from app.api.routers.plan_validations import router as plan_validation_router
from app.api.routers.plans import router as plan_router
from app.api.routers.plantings import router as planting_router
from app.api.routers.project_files import router as project_file_router
from app.api.routers.projects import router as project_router

router = APIRouter()

router.include_router(analysis_router)
router.include_router(config_snapshot_router)
router.include_router(file_artifact_router)
router.include_router(job_router)
router.include_router(plan_router)
router.include_router(plan_validation_router)
router.include_router(planting_router)
router.include_router(project_router)
router.include_router(project_file_router)
