from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.endpoints import router as api_endpoint_router
from app.core.config.exception_handlers import register_exception_handlers
from app.core.config.logger import configure_logger
from app.core.config.manager import settings
from app.core.config.monitoring import configure_sentry, flush_sentry
from app.core.db.database import async_db


def init_backend_app() -> FastAPI:

    configure_logger()
    configure_sentry(service_name='api')

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info(
            'Приложение Автосад запущено: debug={}, api_prefix={}',
            settings.DEBUG,
            settings.API_PREFIX,
        )
        try:
            yield
        finally:
            logger.info('Приложение Автосад останавливается')
            await async_db.dispose()
            logger.info('Подключение к базе данных закрыто')
            flush_sentry()

    app = FastAPI(
        **settings.set_backend_app_attributes,
        lifespan=lifespan,
    )

    register_exception_handlers(app=app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.IS_ALLOWED_CREDENTIALS,
        allow_methods=settings.ALLOWED_METHODS,
        allow_headers=settings.ALLOWED_HEADERS,
    )

    static_dir = Path(__file__).resolve().parent / 'static'
    if static_dir.exists():
        app.mount('/static', StaticFiles(directory=static_dir, html=True), name='static')

        @app.get('/', include_in_schema=False)
        async def frontend() -> RedirectResponse:
            return RedirectResponse(url='/static/')

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
