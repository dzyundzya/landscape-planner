from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool

from app.core.config.manager import settings


class AsyncDatabase:
    """Управляет подключением и асинхронными сессиями базы данных."""

    def __init__(self) -> None:
        self.async_engine: AsyncEngine = create_async_engine(
            url=settings.database_url,
            echo=settings.IS_DB_ECHO_LOG,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_POOL_OVERFLOW,
            pool_timeout=settings.DB_TIMEOUT,
        )
        self.async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            expire_on_commit=settings.IS_DB_EXPIRE_ON_COMMIT,
            autoflush=False,
        )

    @property
    def pool(self) -> Pool:
        return self.async_engine.pool

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session_maker() as session:
            try:
                yield session
            # TODO не забудь сделать кастомный ексепшен
            except Exception:
                await session.rollback()
                logger.exception('Транзакция базы данных отменена из-за непредвиденной ошибки')
                raise

    async def dispose(self) -> None:
        await self.async_engine.dispose()


async_db = AsyncDatabase()
