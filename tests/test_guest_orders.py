"""Tests for GuestOrderRepository helpers used by the hardening pass."""

import asyncio
import inspect

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.guest import guest_receipt_received
from db.models import Base, GuestOrder
from db.repository import GuestOrderRepository


async def _make_session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_get_pending_for_user_returns_only_pending(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            repo = GuestOrderRepository(session)
            await repo.create(
                111, 1, receipt_kind="text", receipt_text="paid"
            )
            approved = await repo.create(
                222, 1, receipt_kind="text", receipt_text="paid"
            )
            await repo.mark_approved(approved.id, client_record_id=999)

            pending = await repo.get_pending_for_user(111)
            assert pending is not None
            assert pending.telegram_id == 111

            none_for_222 = await repo.get_pending_for_user(222)
            assert none_for_222 is None

        await engine.dispose()

    asyncio.run(_run())


def test_count_pending_for_plan(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            repo = GuestOrderRepository(session)
            await repo.create(1, 10, receipt_kind="text", receipt_text="paid")
            await repo.create(2, 10, receipt_kind="text", receipt_text="paid")
            rejected = await repo.create(3, 10, receipt_kind="text", receipt_text="paid")
            await repo.mark_rejected(rejected.id)
            await repo.create(4, 20, receipt_kind="text", receipt_text="paid")

            assert await repo.count_pending_for_plan(10) == 2
            assert await repo.count_pending_for_plan(20) == 1
            assert await repo.count_pending_for_plan(999) == 0

        await engine.dispose()

    asyncio.run(_run())


def test_list_for_telegram_id_orders_newest_first_and_respects_limit(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            repo = GuestOrderRepository(session)
            for i in range(3):
                session.add(
                    GuestOrder(
                        telegram_id=42,
                        plan_id=1,
                        status="pending",
                        receipt_kind="text",
                        receipt_text=f"paid-{i}",
                    )
                )
            await session.commit()

            orders = await repo.list_for_telegram_id(42, limit=2)
            assert len(orders) == 2
            assert orders[0].id > orders[1].id

            other_user = await repo.list_for_telegram_id(999)
            assert other_user == []

        await engine.dispose()

    asyncio.run(_run())


def test_guest_receipt_received_has_rate_limit_check_param() -> None:
    params = inspect.signature(guest_receipt_received).parameters
    assert "rate_limit_check" in params
