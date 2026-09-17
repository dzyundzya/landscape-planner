from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import async_db

DBSession = Annotated[AsyncSession, Depends(async_db.get_session)]
