"""Guest self-service purchase flow: browse plans, pay by card, await admin approval."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards import labels as btn
from bot.keyboards.common import guest_order_review_kb, guest_plan_picker_kb
from bot.states import GuestPurchaseStates, GuestSupportStates
from bot.texts import fa as t
from bot.utils.format_delivery import qr_caption
from bot.utils.qr_vless import InvalidVlessQrError, generate_vless_qr_png
from bot.utils.template_labels import expiry_label
from db.models import Plan
from db.repository import (
    GuestOrderRepository,
    GuestSalesConfigRepository,
    PlanRepository,
    ResellerRepository,
)
from db.session import get_session_factory
from services.client_volume import MIN_CLIENT_VOLUME_GB
from services.guest_sales import SYSTEM_RESELLER_TG_ID
from services.panel_registry import PanelRegistry
from services.panel_resolve import ResellerPanelUnavailableError, xui_for_reseller
from services.reseller_service import ResellerService
from xui.client import XuiError

router = Router()
logger = logging.getLogger(__name__)


async def _pending_order_notice(session, telegram_id: int) -> str | None:
    pending = await GuestOrderRepository(session).get_pending_for_user(telegram_id)
    if pending is None:
        return None
    plan = await session.get(Plan, pending.plan_id)
    return t.GUEST_ORDER_ALREADY_PENDING.format(
        order_id=pending.id, plan_name=plan.name if plan else "?"
    )


@router.message(F.text == btn.BUY_ACCOUNT)
async def buy_account(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        config = await GuestSalesConfigRepository(session).get_or_create()
        if not config.is_enabled:
            await message.answer(t.GUEST_SALES_DISABLED)
            return
        notice = await _pending_order_notice(session, message.from_user.id)
        if notice is not None:
            await message.answer(notice)
            return
        plans = await PlanRepository(session).list_active()
    eligible = [p for p in plans if p.volume_gb >= MIN_CLIENT_VOLUME_GB]
    if not eligible:
        await message.answer(t.GUEST_NO_PLANS)
        return
    await message.answer(t.GUEST_PLAN_LIST_HEADER, reply_markup=guest_plan_picker_kb(eligible))


_ORDER_STATUS_LABELS = {
    "pending": "در انتظار بررسی",
    "approved": "✅ تحویل شده",
    "rejected": "❌ رد شده",
}


@router.message(F.text == btn.MY_ORDERS)
async def guest_my_orders(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        orders = await GuestOrderRepository(session).list_for_telegram_id(
            message.from_user.id
        )
        if not orders:
            await message.answer(t.GUEST_MY_ORDERS_EMPTY)
            return
        lines = [t.GUEST_MY_ORDERS_HEADER]
        for o in orders:
            plan = await session.get(Plan, o.plan_id)
            plan_name = plan.name if plan else "?"
            status_label = _ORDER_STATUS_LABELS.get(o.status, o.status)
            date_label = o.created_at.strftime("%Y-%m-%d") if o.created_at else "?"
            lines.append(f"• #{o.id} — {plan_name} — {status_label} — {date_label}")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("gplan:"))
async def guest_plan_picked(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        config = await GuestSalesConfigRepository(session).get_or_create()
        if not config.is_enabled:
            await callback.answer(t.GUEST_SALES_DISABLED, show_alert=True)
            return
        plan = await PlanRepository(session).get_active(plan_id)
    if plan is None or plan.volume_gb < MIN_CLIENT_VOLUME_GB:
        await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
        return

    await state.update_data(plan_id=plan_id)
    await state.set_state(GuestPurchaseStates.receipt)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.GUEST_PAYMENT_PROMPT.format(
            name=plan.name,
            volume_gb=plan.volume_gb,
            expiry_label=expiry_label(plan.expiry_days),
            price_toman=plan.price_toman,
            card_number=config.card_number or "—",
            card_holder=config.card_holder or "—",
        )
    )
    await callback.answer()


async def _notify_admins_of_order(message: Message, order_id: int, plan: Plan) -> None:
    settings = get_settings()
    from_user = message.from_user
    username = f" (@{from_user.username})" if from_user and from_user.username else ""
    text = t.GUEST_ORDER_ADMIN_NOTIFY.format(
        order_id=order_id,
        telegram_id=from_user.id if from_user else "?",
        username=username,
        name=plan.name,
        volume_gb=plan.volume_gb,
        expiry_label=expiry_label(plan.expiry_days),
        price_toman=plan.price_toman,
    )
    markup = guest_order_review_kb(order_id)
    for admin_id in settings.admin_telegram_ids:
        try:
            if message.photo:
                await message.bot.send_photo(  # type: ignore[union-attr]
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=text,
                    reply_markup=markup,
                )
            else:
                await message.bot.send_message(  # type: ignore[union-attr]
                    admin_id, text, reply_markup=markup
                )
        except Exception as e:
            logger.warning("Could not notify admin %s of guest order: %s", admin_id, e)


@router.message(GuestPurchaseStates.receipt)
async def guest_receipt_received(
    message: Message, state: FSMContext, rate_limit_check
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    plan_id = data.get("plan_id")
    if plan_id is None:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return

    if not rate_limit_check(message.from_user.id, get_settings().guest_order_rate_limit):
        await message.answer(t.RATE_LIMITED)
        return

    if message.photo:
        receipt_kind = "photo"
        receipt_file_id = message.photo[-1].file_id
        receipt_text = None
    elif message.text:
        receipt_kind = "text"
        receipt_file_id = None
        receipt_text = message.text
    else:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        plan = await PlanRepository(session).get_active(int(plan_id))
        if plan is None:
            await state.clear()
            await message.answer(t.PLAN_NOT_FOUND)
            return
        notice = await _pending_order_notice(session, message.from_user.id)
        if notice is not None:
            await state.clear()
            await message.answer(notice)
            return
        order = await GuestOrderRepository(session).create(
            message.from_user.id,
            int(plan_id),
            username=message.from_user.username,
            receipt_kind=receipt_kind,
            receipt_file_id=receipt_file_id,
            receipt_text=receipt_text,
        )

    await state.clear()
    await message.answer(t.GUEST_ORDER_SUBMITTED)
    await _notify_admins_of_order(message, order.id, plan)


@router.callback_query(F.data.regexp(r"^gqr:[^:]+:\d+$"))
async def guest_send_vless_qr(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    data = callback.data or ""
    try:
        _, email, idx_s = data.split(":", 2)
        index = int(idx_s)
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.message:
        await callback.answer()
        return

    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(SYSTEM_RESELLER_TG_ID)
        if reseller is None:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        try:
            xui = await xui_for_reseller(panel_registry, session, reseller)
        except ResellerPanelUnavailableError:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        svc = ResellerService(session, xui)
        try:
            delivery = await svc.get_delivery(reseller, email)
        except XuiError as e:
            await callback.answer(str(e), show_alert=True)
            return

    if index < 0 or index >= len(delivery.vless_configs):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    cfg = delivery.vless_configs[index]
    try:
        png = generate_vless_qr_png(cfg.link)
    except InvalidVlessQrError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.message.answer_photo(  # type: ignore[union-attr]
        BufferedInputFile(png, filename="vless-qr.png"),
        caption=qr_caption(email, cfg.remark),
    )
    await callback.answer(t.QR_SENT)


@router.message(F.text == btn.SUPPORT)
async def support_start(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.set_state(GuestSupportStates.message)
    await message.answer(t.SUPPORT_PROMPT)


@router.message(GuestSupportStates.message)
async def support_message_received(
    message: Message, state: FSMContext, rate_limit_check
) -> None:
    if not message.from_user:
        return
    if not rate_limit_check(message.from_user.id, get_settings().guest_order_rate_limit):
        await message.answer(t.RATE_LIMITED)
        return

    description = (message.text or message.caption or "").strip()
    if not description and not message.photo:
        await message.answer(t.INVALID_INPUT)
        return

    from_user = message.from_user
    username = f" (@{from_user.username})" if from_user.username else ""
    notify_text = t.SUPPORT_ADMIN_NOTIFY.format(
        telegram_id=from_user.id,
        username=username,
        text=description or "(بدون متن)",
    )
    for admin_id in get_settings().admin_telegram_ids:
        try:
            if message.photo:
                await message.bot.send_photo(  # type: ignore[union-attr]
                    admin_id, photo=message.photo[-1].file_id, caption=notify_text
                )
            else:
                await message.bot.send_message(admin_id, notify_text)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("Could not notify admin %s of support message: %s", admin_id, e)

    await state.clear()
    await message.answer(t.SUPPORT_SENT)
