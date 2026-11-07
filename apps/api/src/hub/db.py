from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hub.config import get_settings


@lru_cache
def build_session_factory() -> async_sessionmaker[AsyncSession] | None:
    database_url = get_settings().database_url
    if not database_url:
        return None
    engine = create_async_engine(database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    session_factory = build_session_factory()
    if session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with session_factory() as session:
        yield session
