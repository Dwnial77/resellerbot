"""Guest order approval: atomic claim, rollback on failure, panel switch."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from db.models import GuestOrder, Panel, Plan, ResellerPanel
from db.repository import GuestOrderRepository, ResellerRepository
from services.guest_sales import (
    SYSTEM_RESELLER_TG_ID,
    deliver_guest_order,
    ensure_system_reseller,
)
from tests.dbutil import make_session_factory
from xui.client import XuiError


def test_second_claim_of_same_order_fails(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            order = await GuestOrderRepository(s).create(
                1, 1, receipt_kind="text", receipt_text="paid"
            )
        async with factory() as s1, factory() as s2:
            assert await GuestOrderRepository(s1).claim_pending(order.id) is True
            assert await GuestOrderRepository(s2).claim_pending(order.id) is False
            assert await GuestOrderRepository(s2).reject_if_pending(order.id) is False
            assert await GuestOrderRepository(s1).release_claim(order.id) is True
            assert await GuestOrderRepository(s2).reject_if_pending(order.id) is True
        async with factory() as s:
            assert (await s.get(GuestOrder, order.id)).status == "rejected"
        await engine.dispose()

    asyncio.run(_run())


async def _seed_panels(session, *ids: int) -> None:
    for pid in ids:
        session.add(Panel(id=pid, name=f"P{pid}", base_url="https://p", api_token="t"))
    await session.commit()


def test_failed_delivery_returns_system_quota(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            await _seed_panels(s, 1)
            await ensure_system_reseller(s, 1, [1])
            plan = Plan(name="p", volume_gb=30, expiry_days=30, price_toman=1)
            s.add(plan)
            await s.commit()
            order = await GuestOrderRepository(s).create(
                1, plan.id, receipt_kind="text", receipt_text="paid"
            )
            config = AsyncMock(panel_id=1, inbound_ids="[1]")
            with patch(
                "services.guest_sales.xui_for_reseller_panel",
                AsyncMock(return_value=AsyncMock()),
            ), patch(
                "services.guest_sales.ResellerService.create_service",
                AsyncMock(side_effect=XuiError("panel down")),
            ):
                with pytest.raises(XuiError):
                    await deliver_guest_order(s, AsyncMock(), order, plan, config)
            row = await ResellerRepository(s).get(SYSTEM_RESELLER_TG_ID)
            await s.refresh(row)
            assert row.quota_bytes == 0
        await engine.dispose()

    asyncio.run(_run())


def test_system_reseller_follows_guest_panel_change(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            await _seed_panels(s, 1, 2)
            await ensure_system_reseller(s, 1, [1])
            row = await ensure_system_reseller(s, 2, [7])
            assert row.panel_id == 2
            assignment = await s.scalar(
                select(ResellerPanel).where(
                    ResellerPanel.reseller_tg_id == SYSTEM_RESELLER_TG_ID,
                    ResellerPanel.panel_id == 2,
                )
            )
            assert assignment is not None
            assert assignment.allowed_inbound_ids == "[7]"
        await engine.dispose()

    asyncio.run(_run())
