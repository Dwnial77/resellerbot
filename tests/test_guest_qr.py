"""Tests for on-demand QR delivery in the guest purchase flow."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.guest import guest_send_vless_qr
from bot.keyboards.common import guest_vless_qr_kb
from db.models import Base, ClientRecord, Panel
from services.guest_sales import ensure_system_reseller
from xui.client import ClientDelivery, VlessConfig


def _configs(n: int) -> list[VlessConfig]:
    return [VlessConfig(link=f"vless://abc{i}", remark=f"cfg{i}") for i in range(n)]


def test_guest_vless_qr_kb_uses_gqr_prefix() -> None:
    kb = guest_vless_qr_kb("guest1_5", _configs(2))
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks == ["gqr:guest1_5:0", "gqr:guest1_5:1"]


async def _make_session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_guest_send_vless_qr_sends_photo_for_requested_index(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            session.add(
                Panel(
                    id=1,
                    name="Main",
                    base_url="https://x",
                    api_token="t",
                    verify_ssl=True,
                    auto_vision_flow=True,
                    auto_reseller_group=True,
                    is_active=True,
                )
            )
            await session.commit()
            await ensure_system_reseller(session, 1, [1])
            session.add(
                ClientRecord(
                    reseller_tg_id=0,
                    panel_id=1,
                    email="guest1_5",
                    sub_id="sub-abc",
                    inbound_ids="[1]",
                    allocated_bytes=1000,
                    expiry_time=0,
                )
            )
            await session.commit()

        xui = AsyncMock()
        xui.get_client_delivery = AsyncMock(
            return_value=ClientDelivery(
                vless_configs=_configs(2), subscription_links=[]
            )
        )
        registry = MagicMock()
        registry.get_client.return_value = xui

        async with factory() as session:
            import bot.handlers.guest as guest_module

            original_factory = guest_module.get_session_factory
            guest_module.get_session_factory = lambda: factory
            try:
                callback = MagicMock()
                callback.data = "gqr:guest1_5:1"
                callback.message = AsyncMock()
                callback.answer = AsyncMock()

                await guest_send_vless_qr(callback, registry)
            finally:
                guest_module.get_session_factory = original_factory

            callback.message.answer_photo.assert_awaited_once()
            _, kwargs = callback.message.answer_photo.await_args
            assert "cfg1" in kwargs["caption"]
            callback.answer.assert_awaited_once()

        await engine.dispose()

    asyncio.run(_run())
