"""Guest single sales: order snapshot, accounts ownership, renewal, keyboards."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bot.keyboards.common import (
    guest_account_detail_kb,
    guest_main_kb,
    guest_order_review_kb,
    guest_payment_kb,
    guest_plan_picker_kb,
)
from db.migrations import migrate_010_guest_orders_snapshot
from db.models import ClientRecord, GuestOrder, Panel, Plan, Reseller
from db.repository import GuestOrderRepository, ResellerRepository
from services.guest_sales import (
    SYSTEM_RESELLER_TG_ID,
    deliver_guest_order,
    ensure_system_reseller,
    order_terms,
    renew_guest_order,
)
from services.reseller_service import ResellerService
from tests.dbutil import make_session_factory
from xui.client import XuiError, gb_to_bytes

DAY_MS = 86400 * 1000


def _plan(**kw) -> Plan:
    base = dict(id=1, name="p", volume_gb=30, expiry_days=30, price_toman=150000)
    base.update(kw)
    return Plan(**base)


def test_order_terms_prefer_snapshot_over_current_plan() -> None:
    order = GuestOrder(volume_gb=30, expiry_days=30)
    edited_plan = _plan(volume_gb=100, expiry_days=90)
    assert order_terms(order, edited_plan) == (30.0, 30)
    assert order_terms(order, None) == (30.0, 30)
    assert order_terms(GuestOrder(), edited_plan) == (100.0, 90)
    assert order_terms(GuestOrder(), None) is None


def test_migration_010_adds_columns_to_old_table() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE guest_orders (id INTEGER PRIMARY KEY, status VARCHAR)")
            )
            await conn.run_sync(migrate_010_guest_orders_snapshot)
            await conn.run_sync(migrate_010_guest_orders_snapshot)  # idempotent
            cols = {
                r[1]
                for r in (await conn.execute(text("PRAGMA table_info(guest_orders)")))
            }
        await engine.dispose()
        assert {"kind", "target_client_record_id", "volume_gb", "expiry_days",
                "price_toman"} <= cols

    asyncio.run(_run())


async def _seed_account(session, *, owner: int = 555) -> ClientRecord:
    session.add(Panel(id=1, name="P", base_url="https://p", api_token="t"))
    await session.commit()
    await ensure_system_reseller(session, 1, [1])
    record = ClientRecord(
        reseller_tg_id=SYSTEM_RESELLER_TG_ID, panel_id=1, email="guest-a",
        inbound_ids="[1]", allocated_bytes=gb_to_bytes(30), expiry_time=0,
    )
    session.add(record)
    await session.commit()
    session.add(GuestOrder(telegram_id=owner, plan_id=1, status="approved",
                           receipt_kind="text", client_record_id=record.id))
    session.add(GuestOrder(telegram_id=owner, plan_id=1, status="pending",
                           receipt_kind="text"))
    await session.commit()
    return record


def test_delivered_accounts_are_owned_only_by_buyer(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            record = await _seed_account(s)
            repo = GuestOrderRepository(s)
            assert [r.id for r in await repo.list_delivered_records(555)] == [record.id]
            assert await repo.list_delivered_records(777) == []
            assert await repo.owns_record(555, record.id) is True
            assert await repo.owns_record(777, record.id) is False
        await engine.dispose()

    asyncio.run(_run())


def test_order_create_stores_plan_snapshot(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            order = await GuestOrderRepository(s).create(
                1, 1, receipt_kind="text", receipt_text="x",
                plan=_plan(volume_gb=50, expiry_days=60, price_toman=99000),
                kind="renew", target_client_record_id=7,
            )
            assert (order.volume_gb, order.expiry_days, order.price_toman) == (50, 60, 99000)
            assert (order.kind, order.target_client_record_id) == ("renew", 7)
        await engine.dispose()

    asyncio.run(_run())


def _renew_svc(xui) -> tuple[ResellerService, Reseller]:
    reseller = Reseller(
        telegram_id=0, panel_id=1, quota_bytes=gb_to_bytes(100),
        lifetime_allocated_bytes=gb_to_bytes(30), allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]", is_active=True,
    )
    svc = ResellerService(AsyncMock(), xui)
    svc.client_repo = AsyncMock()
    record = ClientRecord(id=3, reseller_tg_id=0, panel_id=1, email="guest-a",
                          inbound_ids="[1]", allocated_bytes=gb_to_bytes(30),
                          expiry_time=0)
    svc.client_repo.get_for_reseller_email = AsyncMock(return_value=record)
    svc.client_repo.set_allocated_bytes = AsyncMock(return_value=record)
    svc.client_repo.set_expiry_time = AsyncMock(return_value=record)
    svc.reseller_repo = AsyncMock()
    svc.quota = AsyncMock()
    svc.quota.validate_renew = AsyncMock(side_effect=lambda _r, _p, gb: gb_to_bytes(gb))
    svc.quota.global_status = AsyncMock(
        return_value=MagicMock(remaining_bytes=gb_to_bytes(70))
    )
    return svc, reseller


async def _renew(svc, reseller, volume_gb, days, **kw):
    with patch("services.reseller_service.UsageAlertRepository.clear", AsyncMock()):
        return await svc.renew_service(reseller, "guest-a", volume_gb, days, **kw)


def test_guest_renewal_extends_from_current_expiry() -> None:
    async def _run() -> None:
        current = int(time.time() * 1000) + 10 * DAY_MS
        xui = AsyncMock()
        xui.get_client = AsyncMock(return_value={"expiryTime": current})
        svc, reseller = _renew_svc(xui)
        result = await _renew(svc, reseller, 50, 30, extend_from_current=True)
        xui.reset_client_traffic.assert_awaited_once_with("guest-a")
        kwargs = xui.update_client_fields.await_args.kwargs
        assert kwargs["total_bytes"] == gb_to_bytes(50)
        assert kwargs["enable"] is True
        assert abs(kwargs["expiry_ms"] - (current + 30 * DAY_MS)) < 5000
        assert result.new_expiry_ms == kwargs["expiry_ms"]
        svc.reseller_repo.add_lifetime_allocated.assert_awaited_once_with(
            0, gb_to_bytes(50)
        )

    asyncio.run(_run())


def test_reseller_renew_config_still_counts_from_now() -> None:
    async def _run() -> None:
        current = int(time.time() * 1000) + 10 * DAY_MS
        xui = AsyncMock()
        xui.get_client = AsyncMock(return_value={"expiryTime": current})
        svc, reseller = _renew_svc(xui)
        before = int(time.time() * 1000)
        await _renew(svc, reseller, 50, 30)
        new_ms = xui.update_client_fields.await_args.kwargs["expiry_ms"]
        assert abs(new_ms - (before + 30 * DAY_MS)) < 5000

    asyncio.run(_run())


def test_guest_renewal_unlimited_plan_and_expired_account() -> None:
    async def _run() -> None:
        xui = AsyncMock()
        xui.get_client = AsyncMock(return_value={"expiryTime": 1000})
        svc, reseller = _renew_svc(xui)
        await _renew(svc, reseller, 50, 0, extend_from_current=True)
        assert xui.update_client_fields.await_args.kwargs["expiry_ms"] == 0

        xui2 = AsyncMock()
        xui2.get_client = AsyncMock(return_value={"expiryTime": 1000})  # long expired
        svc2, reseller2 = _renew_svc(xui2)
        before = int(time.time() * 1000)
        await _renew(svc2, reseller2, 50, 30, extend_from_current=True)
        new_ms = xui2.update_client_fields.await_args.kwargs["expiry_ms"]
        assert new_ms >= before + 30 * DAY_MS - 5000

    asyncio.run(_run())


def test_renew_rejects_without_quota() -> None:
    from services.quota import QuotaExceeded

    async def _run() -> None:
        xui = AsyncMock()
        svc, reseller = _renew_svc(xui)
        svc.quota.validate_renew = AsyncMock(side_effect=QuotaExceeded("no quota"))
        with pytest.raises(XuiError):
            await _renew(svc, reseller, 50, 30, extend_from_current=True)
        xui.update_client_fields.assert_not_called()
        xui.reset_client_traffic.assert_not_called()

    asyncio.run(_run())


def test_failed_renewal_returns_guest_quota(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            record = await _seed_account(s)
            order = GuestOrder(telegram_id=555, plan_id=1, status="processing",
                               receipt_kind="text", kind="renew",
                               target_client_record_id=record.id,
                               volume_gb=50, expiry_days=30)
            s.add(order)
            await s.commit()
            registry = MagicMock()
            registry.get_client.return_value = AsyncMock()
            with patch(
                "services.guest_sales.ResellerService.renew_service",
                AsyncMock(side_effect=XuiError("panel down")),
            ):
                with pytest.raises(XuiError):
                    await renew_guest_order(s, registry, order, None)
            row = await ResellerRepository(s).get(SYSTEM_RESELLER_TG_ID)
            await s.refresh(row)
            assert row.quota_bytes == 0
        await engine.dispose()

    asyncio.run(_run())


def test_renewal_rejects_record_of_regular_reseller(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            await _seed_account(s)
            other = ClientRecord(reseller_tg_id=42, panel_id=1, email="ali-x",
                                 inbound_ids="[1]", allocated_bytes=1, expiry_time=0)
            s.add(other)
            await s.commit()
            order = GuestOrder(telegram_id=555, plan_id=1, status="processing",
                               receipt_kind="text", kind="renew",
                               target_client_record_id=other.id,
                               volume_gb=50, expiry_days=30)
            with pytest.raises(XuiError):
                await renew_guest_order(s, MagicMock(), order, None)
        await engine.dispose()

    asyncio.run(_run())


def test_deliver_uses_snapshot_volume(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            s.add(Panel(id=1, name="P", base_url="https://p", api_token="t"))
            await s.commit()
            order = GuestOrder(id=9, telegram_id=1, plan_id=1, receipt_kind="text",
                               volume_gb=30, expiry_days=30)
            config = MagicMock(panel_id=1, inbound_ids="[1]")
            create = AsyncMock(return_value=("rec", "delivery"))
            with patch("services.guest_sales.xui_for_reseller_panel",
                       AsyncMock(return_value=AsyncMock())), \
                 patch("services.guest_sales.ResellerService.create_service", create):
                await deliver_guest_order(s, MagicMock(), order,
                                          _plan(volume_gb=100, expiry_days=90), config)
            assert create.await_args.kwargs["volume_gb"] == 30
            assert create.await_args.kwargs["expiry_days"] == 30
        await engine.dispose()

    asyncio.run(_run())


def _buttons(markup):
    rows = getattr(markup, "inline_keyboard", None) or markup.keyboard
    return [b for row in rows for b in row]


def test_purchase_buttons_are_colored() -> None:
    buy = _buttons(guest_main_kb())[0]
    assert buy.style == "success"
    plans = _buttons(guest_plan_picker_kb([_plan()]))
    assert plans[0].style == "success" and plans[0].callback_data == "gplan:1"
    review = _buttons(guest_order_review_kb(12))
    assert [b.style for b in review] == ["success", "danger"]
    detail = _buttons(guest_account_detail_kb(3))
    assert {b.callback_data: b.style for b in detail}["gacc:renew:3"] == "success"


def test_payment_kb_copies_card_and_can_cancel() -> None:
    copy_btn, cancel_btn = _buttons(guest_payment_kb("6037-9975 1234 5678"))
    assert copy_btn.copy_text.text == "6037997512345678"
    assert cancel_btn.callback_data == "gpay:cancel" and cancel_btn.style == "danger"
    assert len(_buttons(guest_payment_kb(None))) == 1


def test_renew_picker_callbacks_fit_telegram_limit() -> None:
    kb = guest_plan_picker_kb([_plan(id=10**9)], renew_record_id=10**9)
    for b in _buttons(kb):
        assert len(b.callback_data.encode()) <= 64
    assert _buttons(kb)[0].callback_data == f"grenew:{10**9}:{10**9}"


def test_account_handlers_refuse_other_users(tmp_path) -> None:
    import bot.handlers.guest as guest_module

    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as s:
            record = await _seed_account(s, owner=555)
        original = guest_module.get_session_factory
        guest_module.get_session_factory = lambda: factory
        try:
            for handler, data in (
                (guest_module.guest_account_detail, f"gacc:v:{record.id}"),
                (guest_module.guest_account_links, f"gacc:link:{record.id}"),
                (guest_module.guest_account_renew, f"gacc:renew:{record.id}"),
            ):
                cb = MagicMock()
                cb.data = data
                cb.from_user.id = 777
                cb.message = AsyncMock()
                cb.answer = AsyncMock()
                kwargs = {"panel_registry": MagicMock()}
                if handler is not guest_module.guest_account_links:
                    kwargs["state"] = AsyncMock()
                if handler is guest_module.guest_account_renew:
                    kwargs.pop("panel_registry")
                    async with factory() as s:
                        from db.repository import GuestSalesConfigRepository

                        await GuestSalesConfigRepository(s).update(is_enabled=True)
                await handler(cb, **kwargs)
                cb.message.edit_text.assert_not_called()
                cb.message.answer.assert_not_called()
                cb.answer.assert_awaited_once()
        finally:
            guest_module.get_session_factory = original
        await engine.dispose()

    asyncio.run(_run())
