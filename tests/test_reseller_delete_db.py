"""ResellerRepository.delete against a real SQLite database."""

import asyncio

from sqlalchemy import select

from db.models import ResellerPanel
from db.repository import ResellerRepository
from tests.dbutil import make_session_factory, seed_reseller


def test_delete_reseller_with_panel_assignment(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as session:
            await seed_reseller(session)
            assert await session.scalar(select(ResellerPanel)) is not None
            assert await ResellerRepository(session).delete(100) is True
        async with factory() as session:
            assert await ResellerRepository(session).get(100) is None
            assert await session.scalar(select(ResellerPanel)) is None
        await engine.dispose()

    asyncio.run(_run())
