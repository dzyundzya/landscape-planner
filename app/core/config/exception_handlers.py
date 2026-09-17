from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.exceptions.base import AlreadyExistsError, BadRequestError, NotFoundError
from app.services.exceptions.jobs import InvalidJobError, JobStateConflictError
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
