"""Admin review (approve/reject) of pending guest purchase orders."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards.common import guest_vless_qr_kb
from bot.texts import fa as t
from bot.utils.format_delivery import DELIVERY_PARSE_MODE, format_delivery_message
from db.models import Plan
from db.repository import GuestOrderRepository, GuestSalesConfigRepository
from db.session import get_session_factory
from services.guest_sales import deliver_guest_order
from services.panel_registry import PanelRegistry
from services.panel_resolve import ResellerPanelUnavailableError
from services.quota import QuotaExceeded
from xui.client import XuiError

router = Router()


def _parse_order_id(callback: CallbackQuery) -> int | None:
    try:
        return int((callback.data or "").split(":", 2)[2])
    except (ValueError, IndexError):
        return None


async def _edit_review_message(message: Message, text: str) -> None:
    # Photo receipts are forwarded with send_photo; those messages have a
    # caption, not text.
    if message.photo:
        await message.edit_caption(caption=text)
    else:
        await message.edit_text(text)


@router.callback_query(F.data.startswith("gorder:approve:"))
async def guest_order_approve(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    order_id = _parse_order_id(callback)
    if order_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        orders = GuestOrderRepository(session)
        order = await orders.get(order_id)
        if order is None:
            await callback.answer(t.GUEST_ORDER_NOT_FOUND, show_alert=True)
            return
        # Atomic claim: a double click or a second admin gets "not pending"
        # instead of delivering the same order twice.
        if not await orders.claim_pending(order_id):
            await callback.answer(t.GUEST_ORDER_NOT_PENDING, show_alert=True)
            return

        error: str | None = None
        plan = await session.get(Plan, order.plan_id)
        guest_config = await GuestSalesConfigRepository(session).get_or_create()
        if plan is None:
            error = t.GUEST_ORDER_PLAN_DELETED
        elif not guest_config.panel_id or not guest_config.inbound_ids:
            error = t.GUEST_ORDER_NOT_CONFIGURED
        else:
            try:
                record, delivery = await deliver_guest_order(
                    session, panel_registry, order, plan, guest_config
                )
            except (QuotaExceeded, XuiError, ResellerPanelUnavailableError) as e:
                error = str(e) or t.INVALID_INPUT
            except Exception:
                await orders.release_claim(order_id)
                raise
        if error is not None:
            await orders.release_claim(order_id)
            await callback.answer(error, show_alert=True)
            return

        await orders.mark_approved(order.id, record.id)

    delivery_text = format_delivery_message(record.email, delivery, created=True)
    qr_markup = (
        guest_vless_qr_kb(record.email, delivery.vless_configs)
        if delivery.vless_configs
        else None
    )
    try:
        await callback.bot.send_message(  # type: ignore[union-attr]
            order.telegram_id,
            delivery_text,
            parse_mode=DELIVERY_PARSE_MODE,
            reply_markup=qr_markup,
        )
    except Exception as e:
        await callback.answer(f"تحویل داده شد اما ارسال به کاربر ناموفق بود: {e}", show_alert=True)
        return

    if callback.message:
        await _edit_review_message(
            callback.message,  # type: ignore[arg-type]
            t.GUEST_ORDER_APPROVED_ADMIN.format(
                order_id=order.id, telegram_id=order.telegram_id
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("gorder:reject:"))
async def guest_order_reject(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    order_id = _parse_order_id(callback)
    if order_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        orders = GuestOrderRepository(session)
        order = await orders.get(order_id)
        if order is None:
            await callback.answer(t.GUEST_ORDER_NOT_FOUND, show_alert=True)
            return
        if not await orders.reject_if_pending(order_id):
            await callback.answer(t.GUEST_ORDER_NOT_PENDING, show_alert=True)
            return
        telegram_id = order.telegram_id

    try:
        await callback.bot.send_message(telegram_id, t.GUEST_ORDER_REJECTED)  # type: ignore[union-attr]
    except Exception:
        pass

    if callback.message:
        await _edit_review_message(
            callback.message,  # type: ignore[arg-type]
            t.GUEST_ORDER_REJECTED_ADMIN.format(order_id=order_id),
        )
    await callback.answer()
