import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.keyboards.common import guest_plan_picker_kb, plan_admin_hub_kb
from db.models import Base, GuestOrder, Plan
from db.repository import (
    InvalidPlanError,
    PlanHasPendingOrdersError,
    PlanRepository,
    normalize_plan_name,
    validate_plan_params,
)


def test_normalize_plan_name_ok() -> None:
    assert normalize_plan_name("10GB/30روز") == "10GB/30روز"
    assert normalize_plan_name("  my-plan  ") == "my-plan"


def test_normalize_plan_name_empty() -> None:
    with pytest.raises(InvalidPlanError, match="خالی"):
        normalize_plan_name("   ")


def test_normalize_plan_name_too_long() -> None:
    with pytest.raises(InvalidPlanError, match="64"):
        normalize_plan_name("x" * 65)


def test_validate_plan_params_ok() -> None:
    validate_plan_params(10.0, 30, 150000)
    validate_plan_params(0.5, 0, 1)


def test_validate_plan_params_volume() -> None:
    with pytest.raises(InvalidPlanError, match="حجم"):
        validate_plan_params(0, 30, 1000)
    with pytest.raises(InvalidPlanError, match="حجم"):
        validate_plan_params(-1, 30, 1000)


def test_validate_plan_params_expiry() -> None:
    with pytest.raises(InvalidPlanError, match="انقضا"):
        validate_plan_params(10, -1, 1000)


def test_validate_plan_params_price() -> None:
    with pytest.raises(InvalidPlanError, match="قیمت"):
        validate_plan_params(10, 30, 0)
    with pytest.raises(InvalidPlanError, match="قیمت"):
        validate_plan_params(10, 30, -5)


def _plan(id_: int = 1, *, is_active: bool = True, volume_gb: float = 25) -> Plan:
    return Plan(
        id=id_,
        name=f"plan{id_}",
        volume_gb=volume_gb,
        expiry_days=30,
        price_toman=100000,
        sort_order=0,
        is_active=is_active,
    )


def test_plan_admin_hub_kb_toggle_and_delete_buttons() -> None:
    plans = [_plan(1, is_active=True), _plan(2, is_active=False)]
    kb = plan_admin_hub_kb(plans)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "aplan:toggle:1" in callbacks
    assert "aplan:del:1" in callbacks
    assert "aplan:toggle:2" in callbacks
    assert "aplan:add" in callbacks


def test_guest_plan_picker_kb_lists_all_given_plans() -> None:
    plans = [_plan(1), _plan(2)]
    kb = guest_plan_picker_kb(plans)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks == ["gplan:1", "gplan:2"]


def test_guest_plan_picker_kb_hides_plans_below_min_client_volume() -> None:
    plans = [_plan(1, volume_gb=10), _plan(2, volume_gb=25)]
    kb = guest_plan_picker_kb(plans)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks == ["gplan:2"]


async def _make_session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_delete_blocked_by_pending_order(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            plan = await PlanRepository(session).create("p", 25, 30, 100000)
            session.add(
                GuestOrder(
                    telegram_id=1,
                    plan_id=plan.id,
                    status="pending",
                    receipt_kind="text",
                    receipt_text="paid",
                )
            )
            await session.commit()

            with pytest.raises(PlanHasPendingOrdersError) as exc_info:
                await PlanRepository(session).delete(plan.id)
            assert exc_info.value.count == 1

            still_there = await session.get(Plan, plan.id)
            assert still_there is not None

        await engine.dispose()

    asyncio.run(_run())


def test_delete_allowed_when_no_pending_orders(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await _make_session_factory(tmp_path)
        async with factory() as session:
            plan = await PlanRepository(session).create("p", 25, 30, 100000)
            session.add(
                GuestOrder(
                    telegram_id=1,
                    plan_id=plan.id,
                    status="approved",
                    receipt_kind="text",
                    receipt_text="paid",
                )
            )
            await session.commit()

            deleted = await PlanRepository(session).delete(plan.id)
            assert deleted is True
            assert await session.get(Plan, plan.id) is None

        await engine.dispose()

    asyncio.run(_run())
