from typing import Annotated

from pydantic import BaseModel, Field


class PageResponseSchema[SchemaType](BaseModel):
    """Базовая схема ответа с пагинацией."""

    total: Annotated[int, Field(ge=0, description='Общее количество объектов')]
    page: Annotated[int, Field(ge=1, description='Номер текущей страницы')]
    limit: Annotated[int, Field(ge=1, le=100, description='Максимальное количество объектов на странице')]
    pages: Annotated[int, Field(ge=0, description='Общее количество страниц')]
    items: Annotated[list[SchemaType], Field(description='Список объектов на текущей странице')]
