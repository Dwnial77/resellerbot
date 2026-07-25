"""Tests for the guest self-service delivery path (system reseller provisioning)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Base, GuestOrder, GuestSalesConfig, Panel, Plan
from db.repository import ResellerRepository, inbound_ids_to_json
from services.guest_sales import (
    SYSTEM_RESELLER_TG_ID,
    deliver_guest_order,
    ensure_system_reseller,
)
from xui.client import ClientDelivery, gb_to_bytes


async def _make_session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _panel(panel_id: int = 1) -> Panel:
    return Panel(
        id=panel_id,
        name="Main",
        base_url="https://x",
        api_token="t",
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=True,
    )


def _fake_xui():
    xui = AsyncMock()
    xui.auto_reseller_group = False
    xui.sub_public_url = None
    xui.get_client = AsyncMock(return_value=None)
    xui.create_client = AsyncMock(return_value=(object(), "sub-abc"))
    xui.get_client_delivery = AsyncMock(
        return_value=ClientDelivery(vless_configs=[], subscription_links=[])
    )
    return xui


def test_ensure_system_reseller_is_idempotent_and_hidden(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            session.add(_panel())
            await session.commit()

        async with factory() as session:
            r1 = await ensure_system_reseller(session, 1, [1])
            r2 = await ensure_system_reseller(session, 1, [1])
            assert r1.telegram_id == SYSTEM_RESELLER_TG_ID
            assert r2.telegram_id == SYSTEM_RESELLER_TG_ID
            assert r1.is_system is True

            repo = ResellerRepository(session)
            assert all(
                r.telegram_id != SYSTEM_RESELLER_TG_ID
                for r in await repo.list_active()
            )
            assert all(
                r.telegram_id != SYSTEM_RESELLER_TG_ID
                for r in await repo.list_all()
            )

        await engine.dispose()

    asyncio.run(_run())


def test_deliver_guest_order_creates_client_and_tops_up_quota(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            session.add(_panel())
            plan = Plan(
                name="10GB/30",
                volume_gb=25,
                expiry_days=30,
                price_toman=100000,
                sort_order=1,
                is_active=True,
            )
            session.add(plan)
            config = GuestSalesConfig(
                id=1,
                panel_id=1,
                inbound_ids=inbound_ids_to_json([1]),
                card_number="1234",
                card_holder="Admin",
                is_enabled=True,
            )
            session.add(config)
            await session.commit()
            await session.refresh(plan)
            order = GuestOrder(
                telegram_id=555,
                plan_id=plan.id,
                status="pending",
                receipt_kind="text",
                receipt_text="paid",
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            plan_id, order_id = plan.id, order.id

        xui = _fake_xui()
        registry = MagicMock()
        registry.get_client.return_value = xui

        async with factory() as session:
            plan_row = await session.get(Plan, plan_id)
            order_row = await session.get(GuestOrder, order_id)
            config_row = await session.get(GuestSalesConfig, 1)

            record, delivery = await deliver_guest_order(
                session, registry, order_row, plan_row, config_row
            )

            assert record.allocated_bytes == gb_to_bytes(25)
            assert record.reseller_tg_id == SYSTEM_RESELLER_TG_ID
            xui.create_client.assert_awaited_once()

            system = await ResellerRepository(session).get(SYSTEM_RESELLER_TG_ID)
            assert system is not None
            assert system.quota_bytes == gb_to_bytes(25)
            assert system.lifetime_allocated_bytes == gb_to_bytes(25)

        await engine.dispose()

    asyncio.run(_run())


def test_deliver_guest_order_second_purchase_tops_up_further(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            session.add(_panel())
            plan = Plan(
                name="5GB/30",
                volume_gb=20,
                expiry_days=30,
                price_toman=50000,
                sort_order=1,
                is_active=True,
            )
            session.add(plan)
            config = GuestSalesConfig(
                id=1,
                panel_id=1,
                inbound_ids=inbound_ids_to_json([1]),
                card_number="1234",
                card_holder="Admin",
                is_enabled=True,
            )
            session.add(config)
            await session.commit()
            await session.refresh(plan)
            plan_id = plan.id

        xui = _fake_xui()
        registry = MagicMock()
        registry.get_client.return_value = xui

        for buyer_id in (111, 222):
            async with factory() as session:
                order = GuestOrder(
                    telegram_id=buyer_id,
                    plan_id=plan_id,
                    status="pending",
                    receipt_kind="text",
                    receipt_text="paid",
                )
                session.add(order)
                await session.commit()
                await session.refresh(order)

                plan_row = await session.get(Plan, plan_id)
                config_row = await session.get(GuestSalesConfig, 1)
                await deliver_guest_order(session, registry, order, plan_row, config_row)

        async with factory() as session:
            system = await ResellerRepository(session).get(SYSTEM_RESELLER_TG_ID)
            assert system.quota_bytes == gb_to_bytes(40)
            assert system.lifetime_allocated_bytes == gb_to_bytes(40)

        await engine.dispose()

    asyncio.run(_run())
