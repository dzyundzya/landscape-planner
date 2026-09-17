from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ProjectModel


@pytest_asyncio.fixture(loop_scope='session')
async def project(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[ProjectModel, None]:
    """Создаёт проект в тестовой БД."""

    async with test_sessionmaker() as session:
        project_obj = ProjectModel(
            name='Тестовый участок',
            description='Проект для интеграционного теста',
        )
        session.add(project_obj)
        await session.commit()
        await session.refresh(project_obj)

    yield project_obj
