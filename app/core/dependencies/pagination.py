from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass(frozen=True, slots=True)
class PaginationParams:
    """Параметры пагинации."""

    page: int
    limit: int


def get_pagination_params(
    page: Annotated[int, Query(ge=1, description='Номер страницы')] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description='Количество объектов на странице')] = 20,
) -> PaginationParams:
    """Возвращает параметры пагинации из query-параметров."""

    return PaginationParams(page=page, limit=limit)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]
