from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.core.config.logger import configure_logger
from app.core.config.manager import settings
from app.core.db.database import async_db
from app.api.endpoints import router as api_endpoint_router


def init_backend_app() -> FastAPI:

    configure_logger()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.warning(
            'Приложение Landscape planner запущено: debug={}, api_prefix={}',
            settings.DEBUG,
            settings.API_PREFIX,
        )
        yield
        logger.warning('Приложение Landscape planner останавливается')
        await async_db.dispose()
        logger.warning('Подключение к базе данных закрыто')

    app = FastAPI(
        **settings.set_backend_app_attributes,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.IS_ALLOWED_CREDENTIALS,
        allow_methods=settings.ALLOWED_METHODS,
        allow_headers=settings.ALLOWED_HEADERS,
    )

    static_dir = Path(__file__).resolve().parent / 'static'
    if static_dir.exists():
        app.mount('/static', StaticFiles(directory=static_dir), name='static')

    app.include_router(router=api_endpoint_router, prefix=settings.API_PREFIX)

    return app

backend_app: FastAPI = init_backend_app()

@backend_app.get('/health')
async def health_check() -> dict[str, str]:
    return {'status': 'ok'}


if __name__ == '__main__':
    uvicorn.run(
        app='app.main:backend_app',
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOGGING_LEVEL,
    )
