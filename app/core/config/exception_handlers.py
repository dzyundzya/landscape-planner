from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.exceptions.analyses import AnalysisSourceNotReadyError, InvalidAnalysisError
from app.services.exceptions.base import AlreadyExistsError, BadRequestError, NotFoundError
from app.services.exceptions.config_snapshots import ConfigPrerequisiteError, InvalidConfigSnapshotError
from app.services.exceptions.file_artifacts import (
    FileArtifactTooLargeError,
    FileArtifactUnavailableError,
    InvalidFileArtifactError,
)
from app.services.exceptions.jobs import InvalidJobError, JobStateConflictError
from app.services.exceptions.plans import InvalidPlanError, PlanPrerequisiteError
from app.services.exceptions.plantings import (
    InvalidPlanRevisionError,
    PlanRevisionConflictError,
    PlanRevisionRequiredError,
    PlantingValidationError,
)
from app.services.exceptions.project_files import InvalidProjectFileError, ProjectFileTooLargeError


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует глобальные обработчики исключений."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        """Преобразует ошибку отсутствующей сущности в HTTP 404."""

        logger.info(
            'Сущность не найдена: path={}, detail={}',
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={'detail': str(exc)},
        )

    @app.exception_handler(AlreadyExistsError)
    async def already_exists_handler(request: Request, exc: AlreadyExistsError) -> JSONResponse:
        """Преобразует ошибку дубликата сущности в HTTP 409."""

        logger.warning(
            'Конфликт данных: path={}, detail={}',
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(BadRequestError)
    async def bad_request_handler(request: Request, exc: BadRequestError) -> JSONResponse:
        """Преобразует ошибки некорректного запроса в HTTP 400."""

        logger.info(
            'Некорректный запрос: path={}, detail={}',
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidProjectFileError)
    async def invalid_project_file_handler(request: Request, exc: InvalidProjectFileError) -> JSONResponse:
        """Преобразует ошибку исходного файла в HTTP 422."""

        logger.info(
            'Некорректный исходный файл: path={}, detail={}',
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(ProjectFileTooLargeError)
    async def project_file_too_large_handler(request: Request, exc: ProjectFileTooLargeError) -> JSONResponse:
        """Преобразует превышение размера файла в HTTP 413."""

        logger.info(
            'Превышен размер исходного файла: path={}, detail={}',
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidJobError)
    async def invalid_job_handler(request: Request, exc: InvalidJobError) -> JSONResponse:
        """Преобразует некорректные параметры задачи в HTTP 422."""

        logger.info('Некорректная задача: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(JobStateConflictError)
    async def job_state_conflict_handler(request: Request, exc: JobStateConflictError) -> JSONResponse:
        """Преобразует запрещённый переход задачи в HTTP 409."""

        logger.info('Конфликт состояния задачи: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidFileArtifactError)
    async def invalid_file_artifact_handler(request: Request, exc: InvalidFileArtifactError) -> JSONResponse:
        """Преобразует ошибку файла результата в HTTP 422."""

        logger.info('Некорректный файл результата: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(FileArtifactTooLargeError)
    async def file_artifact_too_large_handler(request: Request, exc: FileArtifactTooLargeError) -> JSONResponse:
        """Преобразует превышение размера результата в HTTP 413."""

        logger.info('Превышен размер файла результата: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={'detail': str(exc)},
        )

    @app.exception_handler(FileArtifactUnavailableError)
    async def file_artifact_unavailable_handler(
        request: Request,
        exc: FileArtifactUnavailableError,
    ) -> JSONResponse:
        """Преобразует недоступность зарегистрированного файла в HTTP 409."""

        logger.error('Файл результата недоступен: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(AnalysisSourceNotReadyError)
    async def analysis_source_not_ready_handler(request: Request, exc: AnalysisSourceNotReadyError) -> JSONResponse:
        """Преобразует неготовность исходника к анализу в HTTP 409."""

        logger.info('Исходник не готов к анализу: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidAnalysisError)
    async def invalid_analysis_handler(request: Request, exc: InvalidAnalysisError) -> JSONResponse:
        """Преобразует несогласованный результат анализа в HTTP 422."""

        logger.info('Некорректный результат анализа: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(ConfigPrerequisiteError)
    async def config_prerequisite_handler(request: Request, exc: ConfigPrerequisiteError) -> JSONResponse:
        """Преобразует неготовность проекта к настройке в HTTP 409."""

        logger.info('Проект не готов к настройке: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidConfigSnapshotError)
    async def invalid_config_snapshot_handler(request: Request, exc: InvalidConfigSnapshotError) -> JSONResponse:
        """Преобразует несогласованные настройки в HTTP 422."""

        logger.info('Некорректные настройки проекта: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(PlanPrerequisiteError)
    async def plan_prerequisite_handler(request: Request, exc: PlanPrerequisiteError) -> JSONResponse:
        """Преобразует неготовность проекта к генерации в HTTP 409."""

        logger.info('Проект не готов к генерации: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidPlanError)
    async def invalid_plan_handler(request: Request, exc: InvalidPlanError) -> JSONResponse:
        """Преобразует несогласованный результат генерации в HTTP 422."""

        logger.info('Некорректный план: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(PlantingValidationError)
    async def planting_validation_handler(request: Request, exc: PlantingValidationError) -> JSONResponse:
        """Преобразует невалидную посадку в HTTP 422."""

        logger.info('Посадка отклонена: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(PlanRevisionConflictError)
    async def plan_revision_conflict_handler(request: Request, exc: PlanRevisionConflictError) -> JSONResponse:
        """Преобразует устаревшую ревизию плана в HTTP 409."""

        logger.info('Конфликт ревизии плана: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': str(exc)},
        )

    @app.exception_handler(PlanRevisionRequiredError)
    async def plan_revision_required_handler(request: Request, exc: PlanRevisionRequiredError) -> JSONResponse:
        """Преобразует отсутствие If-Match в HTTP 428."""

        logger.info('Не указана ревизия плана: path={}', request.url.path)
        return JSONResponse(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            content={'detail': str(exc)},
        )

    @app.exception_handler(InvalidPlanRevisionError)
    async def invalid_plan_revision_handler(request: Request, exc: InvalidPlanRevisionError) -> JSONResponse:
        """Преобразует неверный If-Match в HTTP 400."""

        logger.info('Некорректная ревизия плана: path={}, detail={}', request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(exc)},
        )
