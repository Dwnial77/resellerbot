"""Admin wizard and hub for guest-purchasable plans."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.utils.numbers import parse_days, parse_number
from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    plan_admin_hub_kb,
    plan_delete_confirm_kb,
    plan_detail_kb,
    plan_edit_cancel_kb,
    plan_wizard_confirm_kb,
    plan_wizard_expiry_kb,
    plan_wizard_name_kb,
    plan_wizard_price_kb,
    plan_wizard_volume_kb,
)
from bot.states import AddPlanStates, EditPlanStates
from bot.texts import fa as t
from bot.utils.template_labels import (
    expiry_label,
    format_gb,
    format_toman,
    suggest_template_name,
)
from db.models import Plan
from db.repository import (
    InvalidPlanError,
    PlanHasPendingOrdersError,
    PlanRepository,
    normalize_plan_name,
)
from db.session import get_session_factory
from services.client_volume import MIN_CLIENT_VOLUME_GB

router = Router()


def _parse_price(raw: str) -> int:
    """'150000', '150,000', '۱۵۰٬۰۰۰' -> 150000; ValueError if not > 0."""
    text = (raw or "").strip().replace(",", "").replace("٬", "").replace(" ", "")
    price = int(text)
    if price <= 0:
        raise ValueError(price)
    return price


def _volume_too_low_text() -> str:
    return t.PLAN_VOLUME_TOO_LOW.format(min_gb=format_gb(MIN_CLIENT_VOLUME_GB))


def _plan_detail_text(plan: Plan) -> str:
    return t.PLAN_DETAIL.format(
        id=plan.id,
        name=plan.name,
        status="🟢 فعال" if plan.is_active else "🔴 غیرفعال",
        volume_gb=format_gb(plan.volume_gb),
        expiry_label=expiry_label(plan.expiry_days),
        price=format_toman(plan.price_toman),
    )


async def _plan_hub_content() -> tuple[str, object]:
    async with get_session_factory()() as session:
        rows = await PlanRepository(session).list_all()

    if not rows:
        text = f"{t.PLAN_LIST_EMPTY}\n\n{t.PLAN_HUB_HINT}"
    else:
        lines = [t.PLAN_LIST_HEADER]
        for r in rows:
            status = "فعال" if r.is_active else "غیرفعال"
            lines.append(
                f"#{r.id} — {r.name} ({status})\n"
                f"حجم: {format_gb(r.volume_gb)} GB\n"
                f"انقضا: {expiry_label(r.expiry_days)}\n"
                f"قیمت: {format_toman(r.price_toman)} تومان"
            )
        text = "\n\n".join(lines)
    return text, plan_admin_hub_kb(rows)


async def _send_plan_hub(target: Message) -> None:
    text, markup = await _plan_hub_content()
    await target.answer(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_plan_hub(target: Message) -> None:
    text, markup = await _plan_hub_content()
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]


async def _start_add_wizard(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddPlanStates.volume)
    await message.answer(
        t.PLAN_WIZARD_VOLUME,
        reply_markup=plan_wizard_volume_kb(),
    )


async def _go_to_expiry_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlanStates.expiry)
    await message.answer(
        t.PLAN_WIZARD_EXPIRY,
        reply_markup=plan_wizard_expiry_kb(),
    )


async def _go_to_name_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    suggested = suggest_template_name(data["volume_gb"], data["expiry_days"])
    await state.update_data(suggested_name=suggested)
    await state.set_state(AddPlanStates.name)
    await message.answer(
        t.PLAN_WIZARD_NAME.format(suggested=suggested),
        reply_markup=plan_wizard_name_kb(),
    )


async def _go_to_price_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlanStates.price)
    await message.answer(
        t.PLAN_WIZARD_PRICE,
        reply_markup=plan_wizard_price_kb(),
    )


async def _go_to_confirm_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AddPlanStates.confirm)
    await message.answer(
        t.PLAN_WIZARD_CONFIRM.format(
            name=data["name"],
            volume_gb=data["volume_gb"],
            expiry_label=expiry_label(data["expiry_days"]),
            price_toman=format_toman(data["price_toman"]),
        ),
        reply_markup=plan_wizard_confirm_kb(),
    )


@router.message(F.text == btn.GUEST_PLANS)
@router.message(Command("plans"))
async def plan_hub(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await _send_plan_hub(message)


@router.callback_query(F.data == "aplan:hub")
async def plan_hub_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _edit_plan_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "aplan:add")
async def plan_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _start_add_wizard(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


async def _show_plan_detail(message: Message, plan_id: int, *, edit: bool) -> bool:
    async with get_session_factory()() as session:
        plan = await session.get(Plan, plan_id)
    if plan is None:
        return False
    text, markup = _plan_detail_text(plan), plan_detail_kb(plan)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)
    return True


@router.callback_query(F.data.regexp(r"^aplan:view:\d+$"))
async def plan_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message:
        await callback.answer()
        return
    await state.clear()
    plan_id = int((callback.data or "").rsplit(":", 1)[1])
    if not await _show_plan_detail(callback.message, plan_id, edit=True):  # type: ignore[arg-type]
        await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.regexp(r"^aplan:move:(up|down):\d+$"))
async def plan_move(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message:
        await callback.answer()
        return
    _, _, direction, plan_id_s = (callback.data or "").split(":")
    plan_id = int(plan_id_s)
    async with get_session_factory()() as session:
        moved = await PlanRepository(session).move(
            plan_id, -1 if direction == "up" else 1
        )
    if not moved:
        await callback.answer(t.PLAN_MOVE_EDGE)
        return
    await callback.answer()
    await _show_plan_detail(callback.message, plan_id, edit=True)  # type: ignore[arg-type]


@router.callback_query(F.data.regexp(r"^aplan:edit:(name|price|volume|days):\d+$"))
async def plan_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message:
        await callback.answer()
        return
    _, _, field, plan_id_s = (callback.data or "").split(":")
    await state.clear()
    await state.update_data(plan_id=int(plan_id_s), field=field)
    await state.set_state(EditPlanStates.value)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.PLAN_EDIT_PROMPTS[field].format(min_gb=format_gb(MIN_CLIENT_VOLUME_GB)),
        reply_markup=plan_edit_cancel_kb(int(plan_id_s)),
    )
    await callback.answer()


@router.message(EditPlanStates.value)
async def plan_edit_value(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    plan_id, field = data.get("plan_id"), data.get("field")
    raw = message.text or ""
    try:
        if field == "name":
            changes = {"name": raw}
        elif field == "price":
            changes = {"price_toman": _parse_price(raw)}
        elif field == "volume":
            volume = parse_number(raw)
            if volume < MIN_CLIENT_VOLUME_GB:
                await message.answer(_volume_too_low_text())
                return
            changes = {"volume_gb": volume}
        elif field == "days":
            days = parse_days(raw)
            if days < 0:
                raise ValueError(days)
            changes = {"expiry_days": days}
        else:
            await state.clear()
            await message.answer(t.INVALID_INPUT)
            return
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            plan = await PlanRepository(session).update(int(plan_id), **changes)
        except InvalidPlanError as e:
            await message.answer(str(e))
            return
    await state.clear()
    if plan is None:
        await message.answer(t.PLAN_NOT_FOUND)
        return
    await message.answer(t.PLAN_EDIT_SAVED)
    await _show_plan_detail(message, plan.id, edit=False)


@router.callback_query(F.data.startswith("aplan:toggle:"))
async def plan_toggle(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        plan_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        repo = PlanRepository(session)
        row = await session.get(Plan, plan_id)
        if row is None:
            await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
            return
        await repo.set_active(plan_id, not row.is_active)

    await callback.answer()
    await _show_plan_detail(callback.message, plan_id, edit=True)  # type: ignore[arg-type]


@router.callback_query(F.data.startswith("aplan:del:"))
async def plan_delete_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        plan_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        row = await session.get(Plan, plan_id)

    if row is None:
        await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
        return

    await callback.message.edit_text(
        t.PLAN_DELETE_CONFIRM.format(
            id=row.id,
            name=row.name,
            volume_gb=row.volume_gb,
            expiry_label=expiry_label(row.expiry_days),
            price_toman=format_toman(row.price_toman),
        ),
        reply_markup=plan_delete_confirm_kb(row.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("aplan:del_yes:"))
async def plan_delete_confirm(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        plan_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        try:
            deleted = await PlanRepository(session).delete(plan_id)
        except PlanHasPendingOrdersError as e:
            await callback.answer(
                t.PLAN_DELETE_BLOCKED_PENDING.format(count=e.count), show_alert=True
            )
            return

    if not deleted:
        await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
        return

    await callback.answer(t.PLAN_DELETED.format(id=plan_id))
    await _edit_plan_hub(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "aplan:wiz_cancel")
async def plan_wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.PLAN_WIZARD_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("aplan:vol:"))
async def wizard_volume_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    current = await state.get_state()
    if current != AddPlanStates.volume.state:
        await callback.answer()
        return
    try:
        volume = parse_number(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if volume < MIN_CLIENT_VOLUME_GB:
        await callback.answer(_volume_too_low_text(), show_alert=True)
        return
    await state.update_data(volume_gb=volume)
    if callback.message:
        await _go_to_expiry_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddPlanStates.volume)
async def wizard_volume_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        volume = parse_number(message.text or "")
        if volume <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    if volume < MIN_CLIENT_VOLUME_GB:
        await message.answer(_volume_too_low_text())
        return
    await state.update_data(volume_gb=volume)
    await _go_to_expiry_step(message, state)


@router.callback_query(F.data.startswith("aplan:exp:"))
async def wizard_expiry_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    current = await state.get_state()
    if current != AddPlanStates.expiry.state:
        await callback.answer()
        return
    try:
        days = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if days < 0:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(expiry_days=days)
    if callback.message:
        await _go_to_name_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddPlanStates.expiry)
async def wizard_expiry_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        days = parse_days(message.text or "")
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(expiry_days=days)
    await _go_to_name_step(message, state)


@router.callback_query(AddPlanStates.name, F.data == "aplan:use_suggested_name")
async def wizard_use_suggested_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    suggested = data.get("suggested_name")
    if not suggested:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(name=suggested)
    if callback.message:
        await _go_to_price_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddPlanStates.name)
async def wizard_name_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        name = normalize_plan_name(message.text or "")
    except InvalidPlanError as e:
        await message.answer(str(e))
        return
    await state.update_data(name=name)
    await _go_to_price_step(message, state)


@router.message(AddPlanStates.price)
async def wizard_price_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        price = _parse_price(message.text or "")
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(price_toman=price)
    await _go_to_confirm_step(message, state)


@router.callback_query(AddPlanStates.confirm, F.data == "aplan:wiz_save")
async def wizard_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    required = ("name", "volume_gb", "expiry_days", "price_toman")
    if not all(k in data for k in required):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        repo = PlanRepository(session)
        try:
            row = await repo.create(
                data["name"],
                data["volume_gb"],
                data["expiry_days"],
                data["price_toman"],
            )
        except InvalidPlanError as e:
            await callback.answer(str(e), show_alert=True)
            return

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t.PLAN_ADDED.format(
                id=row.id,
                name=row.name,
                volume_gb=row.volume_gb,
                expiry_label=expiry_label(row.expiry_days),
                price_toman=format_toman(row.price_toman),
            )
        )
    await callback.answer()
