from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.exceptions.base import AlreadyExistsError, BadRequestError, NotFoundError


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
