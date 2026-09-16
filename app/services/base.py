from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.crud.base_crud_repository import BaseCRUDRepository


class BaseService[RepositoryType: BaseCRUDRepository]:
    """Базовый дженерик с доступом к репозиторию."""

    repository_class: type[RepositoryType]

    def __init__(self, async_session: AsyncSession) -> None:
        self.session = async_session
        self.repository = self.repository_class(async_session=async_session)
