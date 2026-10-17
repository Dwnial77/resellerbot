"""Quota counters must not lose updates across sessions / concurrent requests."""

import asyncio
from unittest.mock import AsyncMock

from db.repository import ResellerRepository
from services.reseller_service import ResellerService
from tests.dbutil import make_session_factory, seed_reseller
from xui.client import gb_to_bytes


def test_lifetime_updates_from_stale_sessions_are_not_lost(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s0:
            await seed_reseller(s0, quota_bytes=gb_to_bytes(100))
        async with factory() as s1, factory() as s2:
            # Both sessions hold the row before either writes (like two handlers).
            await ResellerRepository(s1).get(100)
            await ResellerRepository(s2).get(100)
            await ResellerRepository(s1).add_lifetime_allocated(100, 10)
            await ResellerRepository(s2).add_lifetime_allocated(100, 5)
            await ResellerRepository(s2).subtract_lifetime_allocated(100, 1)
        async with factory() as s3:
            row = await ResellerRepository(s3).get(100)
            assert row.lifetime_allocated_bytes == 14
            await ResellerRepository(s3).subtract_lifetime_allocated(100, 999)
            await s3.refresh(row)
            assert row.lifetime_allocated_bytes == 0
        await engine.dispose()

    asyncio.run(_run())


def test_operations_for_one_reseller_are_serialized() -> None:
    async def _run() -> None:
        active = 0
        peak = 0

        async def _slow(*_a, **_k):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            raise RuntimeError("stop")

        svc = ResellerService(AsyncMock(), AsyncMock())
        svc.panel_repo = AsyncMock()
        svc.panel_repo.get = AsyncMock(side_effect=_slow)
        reseller = AsyncMock()
        reseller.telegram_id = 4242
        results = await asyncio.gather(
            *[
                svc.create_service(reseller, 20, client_suffix="a", panel_id=1)
                for _ in range(3)
            ],
            return_exceptions=True,
        )
        assert all(isinstance(r, RuntimeError) for r in results)
        assert peak == 1

    asyncio.run(_run())
