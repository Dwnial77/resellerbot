import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.migrations import run_pending_migrations
from db.models import Base


def test_run_pending_migrations_idempotent() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            first = await conn.run_sync(run_pending_migrations)
            second = await conn.run_sync(run_pending_migrations)
        await engine.dispose()
        assert len(first) > 0
        assert second == []

    asyncio.run(_run())
