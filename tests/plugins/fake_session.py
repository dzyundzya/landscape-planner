import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.db.base import Base
from app.core.db.database import async_db
from app.main import backend_app

TEST_DATABASE_URL_ENV = 'TEST_DATABASE_URL'
ROOT_DIR = Path(__file__).resolve().parents[2]


class TestDatabaseSettings(BaseSettings):
    """Настройки тестовой БД."""

    TEST_DATABASE_URL: str | None = None

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / '.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore',
    )


def get_test_database_url() -> str:
    """Возвращает URL отдельной тестовой PostgreSQL БД."""

    test_database_url = os.getenv(TEST_DATABASE_URL_ENV) or TestDatabaseSettings().TEST_DATABASE_URL
    if not test_database_url:
        raise RuntimeError(f'{TEST_DATABASE_URL_ENV} is required for tests')

    database_name = make_url(test_database_url).database
    if database_name is None or 'test' not in database_name.lower():
        raise RuntimeError(f'{TEST_DATABASE_URL_ENV} must point to a dedicated test database')

    return test_database_url


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Создаёт engine и схему отдельной тестовой БД."""

    engine = create_async_engine(
        get_test_database_url(),
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope='session')
async def db_connection(test_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Открывает откатываемую транзакцию на один тест."""

    async with test_engine.connect() as connection:
        transaction = await connection.begin()

        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture(loop_scope='session')
async def test_sessionmaker(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    """Создаёт фабрику сессий внутри тестовой транзакции."""

    return async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode='create_savepoint',
    )


@pytest_asyncio.fixture(loop_scope='session')
async def db_session(test_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    """Возвращает сессию тестовой БД."""

    async with test_sessionmaker() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(loop_scope='session')
async def app_test(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[FastAPI, None]:
    """Подменяет основную DB dependency тестовой сессией."""

    async def get_test_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            try:
                yield session
            finally:
                await session.rollback()

    backend_app.dependency_overrides[async_db.get_session] = get_test_session

    try:
        yield backend_app
    finally:
        backend_app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope='session')
async def client(app_test: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Возвращает асинхронный HTTP-клиент тестового приложения."""

    async with AsyncClient(
        transport=ASGITransport(app=app_test),
        base_url='http://test',
    ) as async_client:
        yield async_client
