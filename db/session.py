import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import get_settings
from db.models import Base
from db.migrations import run_pending_migrations

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_data_dir(url: str) -> None:
    if "sqlite" in url and "///" in url:
        path_part = url.split("///", 1)[-1]
        if path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    global _engine, _session_factory
    settings = get_settings()
    _ensure_data_dir(settings.database_url)
    _engine = create_async_engine(settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        applied = await conn.run_sync(run_pending_migrations)
    if applied:
        import logging

        logging.getLogger(__name__).info(
            "Applied schema revisions: %s", ", ".join(str(r) for r in applied)
        )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


def parse_inbound_ids(raw: str) -> list[int]:
    return json.loads(raw)
