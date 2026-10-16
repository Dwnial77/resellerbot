"""Real (file-backed) SQLite fixtures for repository-level tests."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Base, Panel
from db.repository import ResellerRepository


async def make_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def seed_reseller(session, telegram_id: int = 100, *, quota_bytes: int = 0):
    if await session.get(Panel, 1) is None:
        session.add(Panel(id=1, name="P", base_url="https://p.example", api_token="t"))
        await session.commit()
    return await ResellerRepository(session).upsert(
        telegram_id, quota_bytes, [1], panel_id=1, display_name="ali"
    )
