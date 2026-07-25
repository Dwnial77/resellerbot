"""Admin review (approve/reject) of pending guest purchase orders."""

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.handlers.admin import _is_admin
from bot.texts import fa as t
from bot.utils.format_delivery import DELIVERY_PARSE_MODE, format_delivery_message
from bot.utils.qr_vless import InvalidVlessQrError, generate_vless_qr_png
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
        order = await GuestOrderRepository(session).get(order_id)
        if order is None:
            await callback.answer(t.GUEST_ORDER_NOT_FOUND, show_alert=True)
            return
        if order.status != "pending":
            await callback.answer(t.GUEST_ORDER_NOT_PENDING, show_alert=True)
            return

        plan = await session.get(Plan, order.plan_id)
        if plan is None:
            await callback.answer(t.GUEST_ORDER_PLAN_DELETED, show_alert=True)
            return
        guest_config = await GuestSalesConfigRepository(session).get_or_create()
        if not guest_config.panel_id or not guest_config.inbound_ids:
            await callback.answer(t.GUEST_ORDER_NOT_CONFIGURED, show_alert=True)
            return

        try:
            record, delivery = await deliver_guest_order(
                session, panel_registry, order, plan, guest_config
            )
        except (QuotaExceeded, XuiError, ResellerPanelUnavailableError) as e:
            await callback.answer(str(e), show_alert=True)
            return

        await GuestOrderRepository(session).mark_approved(order.id, record.id)

    delivery_text = format_delivery_message(record.email, delivery, created=True)
    try:
        await callback.bot.send_message(  # type: ignore[union-attr]
            order.telegram_id, delivery_text, parse_mode=DELIVERY_PARSE_MODE
        )
        for cfg in delivery.vless_configs:
            try:
                png = generate_vless_qr_png(cfg.link)
            except InvalidVlessQrError:
                continue
            await callback.bot.send_photo(  # type: ignore[union-attr]
                order.telegram_id,
                BufferedInputFile(png, filename="vless-qr.png"),
            )
    except Exception as e:
        await callback.answer(f"تحویل داده شد اما ارسال به کاربر ناموفق بود: {e}", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.GUEST_ORDER_APPROVED_ADMIN.format(
                order_id=order.id, telegram_id=order.telegram_id
            )
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
        order = await GuestOrderRepository(session).get(order_id)
        if order is None:
            await callback.answer(t.GUEST_ORDER_NOT_FOUND, show_alert=True)
            return
        if order.status != "pending":
            await callback.answer(t.GUEST_ORDER_NOT_PENDING, show_alert=True)
            return
        await GuestOrderRepository(session).mark_rejected(order.id)
        telegram_id = order.telegram_id

    try:
        await callback.bot.send_message(telegram_id, t.GUEST_ORDER_REJECTED)  # type: ignore[union-attr]
    except Exception:
        pass

    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.GUEST_ORDER_REJECTED_ADMIN.format(order_id=order_id)
        )
    await callback.answer()
