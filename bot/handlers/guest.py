"""Guest self-service sales: buy or renew by card payment, manage own accounts."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    guest_account_detail_kb,
    guest_accounts_list_kb,
    guest_order_review_kb,
    guest_payment_kb,
    guest_plan_picker_kb,
    guest_vless_qr_kb,
)
from bot.states import GuestPurchaseStates, GuestSupportStates
from bot.texts import fa as t
from bot.utils.format_delivery import (
    DELIVERY_PARSE_MODE,
    format_delivery_message,
    qr_caption,
)
from bot.utils.format_traffic import (
    client_traffic_used_bytes,
    format_bytes,
    format_expiry,
    progress_bar,
)
from bot.utils.markdown import escape_md
from bot.utils.qr_vless import InvalidVlessQrError, generate_vless_qr_png
from bot.utils.template_labels import expiry_label, format_gb, format_toman
from db.models import ClientRecord, Plan
from db.repository import (
    ClientRepository,
    GuestOrderRepository,
    GuestSalesConfigRepository,
    PlanRepository,
    ResellerRepository,
)
from db.session import get_session_factory
from services.client_volume import MIN_CLIENT_VOLUME_GB
from services.guest_sales import SYSTEM_RESELLER_TG_ID
from services.panel_registry import PanelRegistry
from services.panel_resolve import ServicePanelUnavailableError, xui_for_record
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


def _eligible(plans: list[Plan]) -> list[Plan]:
    return [p for p in plans if p.volume_gb >= MIN_CLIENT_VOLUME_GB]


def _plan_list_text(header: str, plans: list[Plan]) -> str:
    lines = [header]
    for p in plans:
        lines.append(
            t.GUEST_PLAN_LINE.format(
                name=p.name,
                volume_gb=format_gb(p.volume_gb),
                expiry_label=expiry_label(p.expiry_days),
                price=format_toman(p.price_toman),
            )
        )
    lines.append(t.GUEST_PLAN_LIST_FOOTER)
    return "".join(lines)


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
        plans = _eligible(await PlanRepository(session).list_active())
    if not plans:
        await message.answer(t.GUEST_NO_PLANS)
        return
    await message.answer(
        _plan_list_text(t.GUEST_PLAN_LIST_HEADER, plans),
        reply_markup=guest_plan_picker_kb(plans),
    )


_ORDER_STATUS_LABELS = {
    "pending": "در انتظار بررسی",
    "processing": "در حال تحویل",
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
            if o.kind == "renew":
                plan_name = f"♻️ تمدید — {plan_name}"
            status_label = _ORDER_STATUS_LABELS.get(o.status, o.status)
            date_label = o.created_at.strftime("%Y-%m-%d") if o.created_at else "?"
            lines.append(f"• #{o.id} — {plan_name} — {status_label} — {date_label}")
    await message.answer("\n".join(lines))


async def _start_payment(
    callback: CallbackQuery,
    state: FSMContext,
    plan_id: int,
    *,
    renew_record_id: int | None = None,
) -> None:
    """Show the invoice for plan_id and wait for the receipt."""
    user_id = callback.from_user.id  # type: ignore[union-attr]
    async with get_session_factory()() as session:
        config = await GuestSalesConfigRepository(session).get_or_create()
        if not config.is_enabled:
            await callback.answer(t.GUEST_SALES_DISABLED, show_alert=True)
            return
        if renew_record_id is not None and not await GuestOrderRepository(
            session
        ).owns_record(user_id, renew_record_id):
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        notice = await _pending_order_notice(session, user_id)
        if notice is not None:
            await callback.answer(notice, show_alert=True)
            return
        plan = await PlanRepository(session).get_active(plan_id)
    if plan is None or plan.volume_gb < MIN_CLIENT_VOLUME_GB:
        await callback.answer(t.PLAN_NOT_FOUND, show_alert=True)
        return

    await state.clear()
    await state.update_data(plan_id=plan_id, renew_record_id=renew_record_id)
    await state.set_state(GuestPurchaseStates.receipt)
    renew_line = (
        t.GUEST_PAYMENT_RENEW_LINE.format(record_id=renew_record_id)
        if renew_record_id is not None
        else ""
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.GUEST_PAYMENT_PROMPT.format(
            renew_line=renew_line,
            name=escape_md(plan.name),
            volume_gb=format_gb(plan.volume_gb),
            expiry_label=expiry_label(plan.expiry_days),
            price=format_toman(plan.price_toman),
            card_number=(config.card_number or "—").replace("`", ""),
            card_holder=escape_md(config.card_holder or "—"),
        ),
        parse_mode="Markdown",
        reply_markup=guest_payment_kb(config.card_number),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^gplan:\d+$"))
async def guest_plan_picked(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    plan_id = int((callback.data or "").split(":", 1)[1])
    await _start_payment(callback, state, plan_id)


@router.callback_query(F.data.regexp(r"^grenew:\d+:\d+$"))
async def guest_renew_plan_picked(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    _, record_id, plan_id = (callback.data or "").split(":")
    await _start_payment(
        callback, state, int(plan_id), renew_record_id=int(record_id)
    )


@router.callback_query(F.data == "gpay:cancel")
async def guest_payment_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.GUEST_PAYMENT_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


async def _notify_admins_of_order(
    message: Message, order_id: int, plan: Plan, *, renew_email: str | None
) -> None:
    settings = get_settings()
    from_user = message.from_user
    username = f" (@{from_user.username})" if from_user and from_user.username else ""
    kind_label = (
        t.GUEST_ORDER_KIND_RENEW.format(email=renew_email)
        if renew_email
        else t.GUEST_ORDER_KIND_NEW
    )
    receipt_line = (
        t.GUEST_ORDER_RECEIPT_TEXT_LINE.format(receipt=message.text[:500])
        if message.text
        else ""
    )
    text = t.GUEST_ORDER_ADMIN_NOTIFY.format(
        kind_label=kind_label,
        order_id=order_id,
        telegram_id=from_user.id if from_user else "?",
        username=username,
        name=plan.name,
        volume_gb=format_gb(plan.volume_gb),
        expiry_label=expiry_label(plan.expiry_days),
        price=format_toman(plan.price_toman),
        receipt_line=receipt_line,
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


# Menu buttons pressed while a receipt is expected are not receipts; they fall
# through to their own handlers (support is registered below this one).
_GUEST_MENU_TEXTS = {btn.BUY_ACCOUNT, btn.MY_ACCOUNTS, btn.MY_ORDERS, btn.SUPPORT}


@router.message(GuestPurchaseStates.receipt, ~F.text.in_(_GUEST_MENU_TEXTS))
async def guest_receipt_received(
    message: Message, state: FSMContext, rate_limit_check
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    plan_id = data.get("plan_id")
    renew_record_id = data.get("renew_record_id")
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

    renew_email: str | None = None
    async with get_session_factory()() as session:
        plan = await PlanRepository(session).get_active(int(plan_id))
        if plan is None:
            await state.clear()
            await message.answer(t.PLAN_NOT_FOUND)
            return
        orders = GuestOrderRepository(session)
        if renew_record_id is not None:
            record = await session.get(ClientRecord, int(renew_record_id))
            if record is None or not await orders.owns_record(
                message.from_user.id, record.id
            ):
                await state.clear()
                await message.answer(t.SERVICE_NOT_FOUND)
                return
            renew_email = record.email
        notice = await _pending_order_notice(session, message.from_user.id)
        if notice is not None:
            await state.clear()
            await message.answer(notice)
            return
        order = await orders.create(
            message.from_user.id,
            int(plan_id),
            username=message.from_user.username,
            receipt_kind=receipt_kind,
            receipt_file_id=receipt_file_id,
            receipt_text=receipt_text,
            plan=plan,
            kind="renew" if renew_record_id is not None else "new",
            target_client_record_id=(
                int(renew_record_id) if renew_record_id is not None else None
            ),
        )

    await state.clear()
    await message.answer(t.GUEST_ORDER_SUBMITTED.format(order_id=order.id))
    await _notify_admins_of_order(message, order.id, plan, renew_email=renew_email)


async def _guest_xui_for_record(panel_registry: PanelRegistry, record: ClientRecord):
    try:
        return xui_for_record(panel_registry, record)
    except ServicePanelUnavailableError:
        return None


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
        user_id = callback.from_user.id if callback.from_user else None
        is_admin = user_id in get_settings().admin_telegram_ids
        if user_id is None or not (
            is_admin
            or await GuestOrderRepository(session).user_owns_service(user_id, email)
        ):
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        reseller = await ResellerRepository(session).get(SYSTEM_RESELLER_TG_ID)
        record = await ClientRepository(session).get_for_reseller_email(
            SYSTEM_RESELLER_TG_ID, email
        )
        if reseller is None or record is None:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        # The account's own panel (the guest-sales panel may have changed since).
        xui = await _guest_xui_for_record(panel_registry, record)
        if xui is None:
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


async def _accounts_overview(user_id: int) -> tuple[str, object | None]:
    async with get_session_factory()() as session:
        records = await GuestOrderRepository(session).list_delivered_records(user_id)
    if not records:
        return t.GUEST_ACCOUNTS_EMPTY, None
    return t.GUEST_ACCOUNTS_HEADER, guest_accounts_list_kb(records)


@router.message(F.text == btn.MY_ACCOUNTS)
async def guest_my_accounts(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    text, markup = await _accounts_overview(message.from_user.id)
    await message.answer(text, reply_markup=markup)  # type: ignore[arg-type]


@router.callback_query(F.data.in_({"gacc:list", "gacc:back"}))
async def guest_my_accounts_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    text, markup = await _accounts_overview(callback.from_user.id)
    if callback.data == "gacc:back":
        await callback.message.edit_text(text, reply_markup=markup)  # type: ignore[union-attr, arg-type]
    else:
        # "gacc:list" sits under delivery/renewal messages: keep those intact.
        await callback.message.answer(text, reply_markup=markup)  # type: ignore[union-attr, arg-type]
    await callback.answer()


async def _owned_record(
    session, user_id: int, record_id: int
) -> ClientRecord | None:
    if not await GuestOrderRepository(session).owns_record(user_id, record_id):
        return None
    return await session.get(ClientRecord, record_id)


@router.callback_query(F.data.regexp(r"^gacc:v:\d+$"))
async def guest_account_detail(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    record_id = int((callback.data or "").rsplit(":", 1)[1])
    async with get_session_factory()() as session:
        record = await _owned_record(session, callback.from_user.id, record_id)
    if record is None:
        await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
        return
    xui = await _guest_xui_for_record(panel_registry, record)
    if xui is None:
        await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
        return
    try:
        traffic = await xui.get_traffic(record.email)
        client = await xui.get_client(record.email) or {}
    except XuiError as e:
        await callback.answer(str(e), show_alert=True)
        return
    used = client_traffic_used_bytes(traffic)
    total = int(record.allocated_bytes or 0)
    bar, percent = progress_bar(used, total)
    try:
        expiry_ms = int(client.get("expiryTime") or record.expiry_time or 0)
    except (TypeError, ValueError):
        expiry_ms = int(record.expiry_time or 0)
    enabled = bool(client.get("enable", True))
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.GUEST_ACCOUNT_DETAIL.format(
            record_id=record.id,
            email=record.email,
            status=t.GUEST_ACCOUNT_ACTIVE if enabled else t.GUEST_ACCOUNT_INACTIVE,
            used=format_bytes(used),
            total=format_bytes(total),
            bar=bar,
            percent=percent,
            expiry=format_expiry(expiry_ms),
        ),
        reply_markup=guest_account_detail_kb(record.id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^gacc:link:\d+$"))
async def guest_account_links(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    record_id = int((callback.data or "").rsplit(":", 1)[1])
    async with get_session_factory()() as session:
        record = await _owned_record(session, callback.from_user.id, record_id)
        reseller = await ResellerRepository(session).get(SYSTEM_RESELLER_TG_ID)
        if record is None or reseller is None:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        xui = await _guest_xui_for_record(panel_registry, record)
        if xui is None:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        try:
            delivery = await ResellerService(session, xui).get_delivery(
                reseller, record.email
            )
        except XuiError as e:
            await callback.answer(str(e), show_alert=True)
            return
    await callback.message.answer(  # type: ignore[union-attr]
        format_delivery_message(record.email, delivery, created=False),
        parse_mode=DELIVERY_PARSE_MODE,
        reply_markup=guest_vless_qr_kb(record.email, delivery.vless_configs),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^gacc:renew:\d+$"))
async def guest_account_renew(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    record_id = int((callback.data or "").rsplit(":", 1)[1])
    async with get_session_factory()() as session:
        config = await GuestSalesConfigRepository(session).get_or_create()
        if not config.is_enabled:
            await callback.answer(t.GUEST_SALES_DISABLED, show_alert=True)
            return
        record = await _owned_record(session, callback.from_user.id, record_id)
        if record is None:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
        notice = await _pending_order_notice(session, callback.from_user.id)
        if notice is not None:
            await callback.answer(notice, show_alert=True)
            return
        plans = _eligible(await PlanRepository(session).list_active())
    if not plans:
        await callback.answer(t.GUEST_NO_PLANS, show_alert=True)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        _plan_list_text(t.GUEST_RENEW_PLAN_HEADER.format(record_id=record_id), plans),
        reply_markup=guest_plan_picker_kb(plans, renew_record_id=record_id),
    )
    await callback.answer()


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
