import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    client_name_kb,
    confirm_create_kb,
    create_cancel_kb,
    delete_confirm_kb,
    expiry_mode_kb,
    reset_traffic_confirm_kb,
    service_detail_kb,
    service_edit_kb,
    service_list_kb,
    template_picker_kb,
    vless_qr_kb,
)
from bot.states import CreateServiceStates, EditServiceStates, ExtendExpiryStates
from bot.texts import fa as t
from bot.utils.edit_service import (
    InvalidEditInputError,
    format_limit_ip_label,
    validate_limit_ip,
    validate_comment,
)
from bot.utils.expiry import InvalidExpiryInputError, parse_expiry_date
from bot.utils.format_delivery import DELIVERY_PARSE_MODE, format_delivery_message
from bot.utils.qr_vless import InvalidVlessQrError, generate_vless_qr_png
from bot.utils.format_traffic import (
    format_expiry,
    format_traffic_message,
    normalize_traffic_data,
)
from db.repository import (
    ClientRepository,
    PanelRepository,
    ResellerRepository,
    ServiceTemplateRepository,
    format_inbound_summary,
    resolve_attach_inbound_ids,
)
from db.session import get_session_factory
from services.quota import QuotaExceeded, QuotaService, format_max_clients_line
from services.reseller_labels import (
    InvalidClientSuffixError,
    build_client_email,
    email_prefix,
    normalize_client_suffix,
)
from services.panel_registry import PanelRegistry
from services.reseller_service import ResellerService
from bot.utils.service_resolve import (
    answer_resolve_callback,
    answer_resolve_message,
    list_accessible_clients,
    open_service_context,
)
from services.panel_resolve import ServiceNotFoundError, ServicePanelUnavailableError
from xui.client import XuiClient, XuiError

router = Router()


async def _abort_if_no_panel(
    target: Message | CallbackQuery, xui: XuiClient | None
) -> bool:
    """Return True if handler should stop (panel client missing)."""
    if xui is not None:
        return False
    if isinstance(target, CallbackQuery):
        await target.answer(t.NO_PANEL_ACCESS, show_alert=True)
    else:
        await target.answer(t.NO_PANEL_ACCESS)
    return True


async def _get_active_reseller(user_id: int):
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(user_id)
    if not reseller or not reseller.is_active:
        return None, None
    return reseller, repo


@router.message(F.text == btn.ACCOUNT_STATUS)
async def account_status(message: Message) -> None:
    if not message.from_user:
        return
    reseller, repo = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await message.answer(t.NOT_RESELLER)
        return
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(message.from_user.id)
        panel = await PanelRepository(session).get(reseller.panel_id)  # type: ignore[union-attr]
        panel_name = panel.name if panel else f"#{reseller.panel_id}"  # type: ignore[union-attr]
        quota = QuotaService(repo)
        st = await quota.status(reseller)  # type: ignore[arg-type]
    inbounds_summary = format_inbound_summary(reseller)  # type: ignore[arg-type]
    display_name = f" {reseller.display_name}" if reseller.display_name else ""  # type: ignore[union-attr]
    await message.answer(
        t.WELCOME_RESELLER.format(
            display_name=display_name,
            panel_id=reseller.panel_id,  # type: ignore[union-attr]
            panel_name=panel_name,
            quota_gb=st.quota_gb,
            used_gb=st.used_gb,
            remaining_gb=st.remaining_gb,
            client_count=st.client_count,
            max_clients_line=format_max_clients_line(st),
            inbounds_summary=inbounds_summary,
        )
    )


async def _prompt_client_name(
    message: Message, state: FSMContext, reseller
) -> None:
    await state.set_state(CreateServiceStates.client_name)
    await message.answer(
        t.CREATE_CLIENT_NAME_PROMPT.format(prefix=email_prefix(reseller)),
        reply_markup=client_name_kb(),
    )


@router.message(F.text == btn.CREATE_SERVICE)
async def start_create(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    reseller, _ = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await message.answer(t.NOT_RESELLER)
        return
    await state.clear()
    async with get_session_factory()() as session:
        templates = await ServiceTemplateRepository(session).list_active()
    if templates:
        await message.answer(
            t.CREATE_PICK_TEMPLATE,
            reply_markup=template_picker_kb(templates),
        )
        return
    await state.set_state(CreateServiceStates.volume)
    await message.answer(
        t.CREATE_VOLUME_PROMPT, reply_markup=create_cancel_kb()
    )


@router.callback_query(F.data == "create:manual")
async def create_manual(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    await state.clear()
    await state.set_state(CreateServiceStates.volume)
    if callback.message:
        await callback.message.answer(  # type: ignore[union-attr]
            t.CREATE_VOLUME_PROMPT, reply_markup=create_cancel_kb()
        )
    await callback.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def create_from_template(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not callback.from_user:
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    try:
        template_id = int((callback.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        tpl = await ServiceTemplateRepository(session).get_active(template_id)
    if not tpl:
        await callback.answer(t.TEMPLATE_NOT_FOUND, show_alert=True)
        return

    await state.clear()
    await state.update_data(
        volume_gb=tpl.volume_gb,
        expiry_days=tpl.expiry_days,
        template_name=tpl.name,
    )
    if callback.message:
        await _prompt_client_name(callback.message, state, reseller)  # type: ignore[arg-type]
        try:
            await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        except Exception:
            pass
    await callback.answer()


@router.message(CreateServiceStates.volume)
async def process_volume(message: Message, state: FSMContext) -> None:
    try:
        volume = float((message.text or "").replace(",", "."))
        if volume <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(volume_gb=volume)
    await state.set_state(CreateServiceStates.expiry)
    await message.answer(
        t.CREATE_EXPIRY_PROMPT, reply_markup=create_cancel_kb()
    )


@router.message(CreateServiceStates.expiry)
async def process_expiry(message: Message, state: FSMContext) -> None:
    try:
        days = int((message.text or "").strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    data = await state.get_data()

    if not message.from_user:
        return
    reseller, _ = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await state.clear()
        await message.answer(t.NOT_RESELLER)
        return

    await state.update_data(expiry_days=days)
    await _prompt_client_name(message, state, reseller)


async def _show_create_confirm(
    message: Message, state: FSMContext, reseller
) -> bool:
    data = await state.get_data()
    volume_gb = data["volume_gb"]
    days = data.get("expiry_days", 0)
    expiry_label = f"{days} روز" if days > 0 else "نامحدود"
    suffix = data.get("client_suffix")
    if not suffix:
        await message.answer(t.INVALID_INPUT)
        return False
    try:
        email_preview = build_client_email(reseller, suffix)
    except InvalidClientSuffixError as e:
        await message.answer(str(e))
        return False

    async with get_session_factory()() as session:
        if await ClientRepository(session).email_exists(
            email_preview, panel_id=reseller.panel_id
        ):
            await message.answer(t.EMAIL_TAKEN)
            await state.set_state(CreateServiceStates.client_name)
            return False

    inbounds = resolve_attach_inbound_ids(reseller)
    template_name = data.get("template_name")
    template_line = f"قالب: {template_name}\n" if template_name else ""
    await state.update_data(email_preview=email_preview)
    await state.set_state(CreateServiceStates.confirm)
    await message.answer(
        t.CREATE_CONFIRM.format(
            email_preview=email_preview,
            template_line=template_line,
            volume_gb=volume_gb,
            expiry_label=expiry_label,
            inbounds=", ".join(str(i) for i in inbounds),
        ),
        reply_markup=confirm_create_kb(),
        parse_mode="Markdown",
    )
    return True


@router.message(CreateServiceStates.client_name)
async def process_client_name(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    reseller, _ = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await state.clear()
        await message.answer(t.NOT_RESELLER)
        return
    try:
        suffix = normalize_client_suffix(message.text or "")
    except InvalidClientSuffixError as e:
        await message.answer(str(e))
        return
    await state.update_data(client_suffix=suffix)
    await _show_create_confirm(message, state, reseller)


@router.callback_query(
    CreateServiceStates.client_name, F.data == "create:auto_name"
)
async def create_auto_name(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not callback.from_user:
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await state.clear()
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    await state.update_data(client_suffix=secrets.token_hex(4))
    if callback.message:
        ok = await _show_create_confirm(callback.message, state, reseller)  # type: ignore[arg-type]
        if ok:
            await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "create:cancel")
async def cancel_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.clear()
    try:
        await callback.message.edit_text(t.CREATE_CANCELLED)
    except Exception:
        await callback.message.answer(t.CREATE_CANCELLED)
    await callback.answer()


@router.callback_query(CreateServiceStates.confirm, F.data == "create:confirm")
async def confirm_create(
    callback: CallbackQuery,
    state: FSMContext,
    rate_limit_check,
    xui: XuiClient | None = None,
) -> None:
    if not callback.from_user:
        return
    if not rate_limit_check(callback.from_user.id, get_settings().create_rate_limit):
        await callback.answer(t.RATE_LIMITED, show_alert=True)
        return
    if await _abort_if_no_panel(callback, xui):
        return

    data = await state.get_data()
    if data.get("create_locked"):
        await callback.answer("در حال ساخت سرویس…", show_alert=True)
        return

    volume_gb = data.get("volume_gb")
    expiry_days = data.get("expiry_days", 0)
    client_suffix = data.get("client_suffix")
    if volume_gb is None or not client_suffix:
        await state.clear()
        await callback.answer(
            "اطلاعات ساخت ناقص یا منقضی شده. دوباره از «ساخت سرویس» شروع کنید.",
            show_alert=True,
        )
        return

    await state.update_data(create_locked=True)

    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(callback.from_user.id)
        if not reseller or not reseller.is_active:
            await state.clear()
            await callback.message.edit_text(t.NOT_RESELLER)  # type: ignore[union-attr]
            await callback.answer()
            return

        svc = ResellerService(session, xui)
        try:
            record, delivery = await svc.create_service(
                reseller,
                volume_gb=volume_gb,
                expiry_days=expiry_days,
                client_suffix=client_suffix,
            )
        except QuotaExceeded as e:
            await state.update_data(create_locked=False)
            await callback.message.edit_text(str(e))  # type: ignore[union-attr]
            await callback.answer()
            return
        except XuiError as e:
            await state.update_data(create_locked=False)
            await callback.message.edit_text(f"خطای پنل: {e}")  # type: ignore[union-attr]
            await callback.answer()
            return

    await state.clear()
    qr_markup = (
        vless_qr_kb(record.email, delivery.vless_configs)
        if delivery.vless_configs
        else None
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        format_delivery_message(
            record.email,
            delivery,
            created=True,
            sub_public_url_configured=bool(
                xui and xui.sub_public_url
            ),
        ),
        parse_mode=DELIVERY_PARSE_MODE,
        reply_markup=qr_markup,
    )
    await callback.answer()


@router.callback_query(F.data == "create:confirm")
async def confirm_create_stale(callback: CallbackQuery) -> None:
    await callback.answer(
        "این دکمه منقضی شده. از «ساخت سرویس» دوباره شروع کنید.",
        show_alert=True,
    )


async def _accessible_service_emails(
    session, registry: PanelRegistry, reseller_tg_id: int
) -> list[str]:
    clients = await list_accessible_clients(session, registry, reseller_tg_id)
    return [c.email for c in clients]


@router.message(F.text == btn.MY_SERVICES)
async def my_services(message: Message, panel_registry: PanelRegistry) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(message.from_user.id)
        if not reseller or not reseller.is_active:
            await message.answer(t.NOT_RESELLER)
            return
        emails = await _accessible_service_emails(
            session, panel_registry, message.from_user.id
        )

    if not emails:
        await message.answer(t.NO_ACCESSIBLE_SERVICES)
        return
    await message.answer(
        "سرویس‌های شما — یکی را انتخاب کنید:",
        reply_markup=service_list_kb(emails),
    )


@router.callback_query(F.data == "svc:back")
async def services_back(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user:
        return
    async with get_session_factory()() as session:
        emails = await _accessible_service_emails(
            session, panel_registry, callback.from_user.id
        )
    if not emails:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
    else:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "سرویس‌های شما:",
            reply_markup=service_list_kb(emails),
        )
    await callback.answer()


def _service_detail_text(email: str, enabled: bool, expiry_ms: int = 0) -> str:
    status = "فعال" if enabled else "غیرفعال"
    return (
        f"سرویس: `{email}`\n"
        f"وضعیت: {status}\n"
        f"انقضا: {format_expiry(expiry_ms)}"
    )


async def _load_service_detail(
    user_id: int, email: str, registry: PanelRegistry
) -> tuple[bool, int]:
    enabled = True
    expiry_ms = 0
    async with open_service_context(registry, user_id, email) as (ctx, session):
        expiry_ms = int(ctx.record.expiry_time or 0)
        svc = ResellerService(session, ctx.xui)
        try:
            traffic = await svc.get_traffic(ctx.reseller, email)
            data = normalize_traffic_data(traffic)
            enabled = bool(data.get("enable", True))
            raw_exp = data.get("expiryTime", data.get("expiry_time", 0))
            try:
                panel_exp = int(raw_exp or 0)
                if panel_exp > 0:
                    expiry_ms = panel_exp
            except (TypeError, ValueError):
                pass
        except XuiError:
            pass
    return enabled, expiry_ms


async def _show_service_detail(
    message: Message,
    email: str,
    user_id: int,
    registry: PanelRegistry,
) -> None:
    enabled, expiry_ms = await _load_service_detail(user_id, email, registry)
    await message.edit_text(
        _service_detail_text(email, enabled, expiry_ms),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(email, enabled=enabled),
    )


@router.callback_query(F.data.startswith("svc:"))
async def service_detail(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if email == "back":
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        enabled, expiry_ms = await _load_service_detail(
            callback.from_user.id, email, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        _service_detail_text(email, enabled, expiry_ms),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(email, enabled=enabled),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^exp:[^:]+$"))
async def expiry_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        enabled, expiry_ms = await _load_service_detail(
            callback.from_user.id, email, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.EXPIRY_CHOOSE_MODE.format(
            email=email,
            expiry_label=format_expiry(expiry_ms),
        ),
        parse_mode="Markdown",
        reply_markup=expiry_mode_kb(email),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exp_add:"))
async def expiry_start_add_days(
    callback: CallbackQuery, state: FSMContext
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    await state.update_data(email=email)
    await state.set_state(ExtendExpiryStates.add_days)
    await callback.message.edit_text(t.EXPIRY_PROMPT_ADD_DAYS)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("exp_date:"))
async def expiry_start_set_date(
    callback: CallbackQuery, state: FSMContext
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    await state.update_data(email=email)
    await state.set_state(ExtendExpiryStates.set_date)
    await callback.message.edit_text(t.EXPIRY_PROMPT_SET_DATE)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("exp_unlim:"))
async def expiry_set_unlimited(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.update_service_expiry(ctx.reseller, email, expiry_ms=0)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer(t.EXPIRY_UPDATED.format(expiry_label=format_expiry(0)))
    try:
        await _show_service_detail(
            callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return


@router.callback_query(F.data.startswith("exp_cancel:"))
async def expiry_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


@router.message(ExtendExpiryStates.add_days)
async def expiry_process_add_days(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    try:
        days = int((message.text or "").strip())
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, message.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                new_ms = await svc.update_service_expiry(
                    ctx.reseller, email, add_days=days
                )
            except XuiError as e:
                await message.answer(str(e))
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return
    await message.answer(
        t.EXPIRY_UPDATED.format(expiry_label=format_expiry(new_ms))
    )


@router.message(ExtendExpiryStates.set_date)
async def expiry_process_set_date(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    try:
        expiry_ms = parse_expiry_date(message.text or "")
    except InvalidExpiryInputError as e:
        await message.answer(str(e))
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, message.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                new_ms = await svc.update_service_expiry(
                    ctx.reseller, email, expiry_ms=expiry_ms
                )
            except XuiError as e:
                await message.answer(str(e))
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return
    await message.answer(
        t.EXPIRY_UPDATED.format(expiry_label=format_expiry(new_ms))
    )


@router.callback_query(F.data.startswith("enable:"))
async def service_enable(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    await _service_set_enabled(callback, enabled=True, panel_registry=panel_registry)


@router.callback_query(F.data.startswith("disable:"))
async def service_disable(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    await _service_set_enabled(
        callback, enabled=False, panel_registry=panel_registry
    )


async def _service_set_enabled(
    callback: CallbackQuery,
    *,
    enabled: bool,
    panel_registry: PanelRegistry,
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user:
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.set_service_enabled(ctx.reseller, email, enabled)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    try:
        enabled, expiry_ms = await _load_service_detail(
            callback.from_user.id, email, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        _service_detail_text(email, enabled, expiry_ms),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(email, enabled=enabled),
    )
    await callback.answer(
        t.SERVICE_ENABLED if enabled else t.SERVICE_DISABLED,
    )


@router.callback_query(F.data.startswith("link:"))
async def service_link(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user:
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                delivery = await svc.get_delivery(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
            service_xui = ctx.xui
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    qr_markup = (
        vless_qr_kb(email, delivery.vless_configs) if delivery.vless_configs else None
    )
    await callback.message.answer(  # type: ignore[union-attr]
        format_delivery_message(
            email,
            delivery,
            created=False,
            sub_public_url_configured=bool(service_xui.sub_public_url),
        ),
        parse_mode=DELIVERY_PARSE_MODE,
        reply_markup=qr_markup,
    )
    await callback.answer()


def _qr_caption(remark: str) -> str:
    remark_line = f"{remark}\n" if remark else ""
    return t.QR_CAPTION.format(remark_line=remark_line)


@router.callback_query(F.data.startswith("qr_menu:"))
async def show_vless_qr_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                delivery = await svc.get_delivery(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    if not delivery.vless_configs:
        await callback.answer(t.QR_NOT_AVAILABLE, show_alert=True)
        return
    await callback.message.answer(  # type: ignore[union-attr]
        t.QR_CHOOSE,
        reply_markup=vless_qr_kb(email, delivery.vless_configs),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^qr:[^:]+:\d+$"))
async def send_vless_qr(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    data = callback.data or ""
    try:
        _, email, idx_s = data.split(":", 2)
        index = int(idx_s)
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                delivery = await svc.get_delivery(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
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
        caption=_qr_caption(cfg.remark),
    )
    await callback.answer(t.QR_SENT)


@router.callback_query(F.data.startswith("traffic:"))
async def service_traffic(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user:
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                traffic = await svc.get_traffic(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.answer(  # type: ignore[union-attr]
        format_traffic_message(email, traffic),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^del:[^:]+$"))
async def service_delete_prompt(callback: CallbackQuery) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(callback.from_user.id)
        if not reseller:
            await callback.answer(t.NOT_RESELLER, show_alert=True)
            return
        record = await ClientRepository(session).get_for_reseller_email(
            reseller.telegram_id, email
        )
        if not record:
            await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
            return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.DELETE_CONFIRM.format(email=email),
        parse_mode="Markdown",
        reply_markup=delete_confirm_kb(email),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_confirm:"))
async def service_delete_confirm(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user:
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.delete_service(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(t.SERVICE_DELETED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("del_cancel:"))
async def service_delete_cancel(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


def _comment_display(comment: str) -> str:
    if not comment:
        return "—"
    if len(comment) <= 80:
        return comment
    return comment[:77] + "..."


async def _show_service_edit_menu(
    message: Message, email: str, user_id: int, registry: PanelRegistry
) -> None:
    limit_ip = 0
    comment = ""
    try:
        async with open_service_context(registry, user_id, email) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                limit_ip, comment = await svc.get_client_panel_fields(
                    ctx.reseller, email
                )
            except XuiError as e:
                await message.edit_text(str(e))
                return
    except ServiceNotFoundError:
        await message.edit_text(t.SERVICE_NOT_FOUND)
        return
    except ServicePanelUnavailableError as e:
        await message.edit_text(
            t.SERVICE_PANEL_UNAVAILABLE.format(panel_id=e.panel_id)
        )
        return
    await message.edit_text(
        t.EDIT_MENU.format(
            email=email,
            limit_ip_label=format_limit_ip_label(limit_ip),
            comment_label=_comment_display(comment),
        ),
        parse_mode="Markdown",
        reply_markup=service_edit_kb(email),
    )


@router.callback_query(F.data.regexp(r"^edit:[^:]+$"))
async def service_edit_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await _show_service_edit_menu(
        callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_back:"))
async def service_edit_back(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


@router.callback_query(F.data.regexp(r"^edit_reset:[^:]+$"))
async def service_edit_reset_prompt(callback: CallbackQuery) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.message:
        await callback.answer()
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RESET_TRAFFIC_CONFIRM.format(email=email),
        parse_mode="Markdown",
        reply_markup=reset_traffic_confirm_kb(email),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_reset_ok:"))
async def service_edit_reset_confirm(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.reset_service_traffic(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer(t.TRAFFIC_RESET_OK)
    await _show_service_edit_menu(
        callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
    )


@router.callback_query(F.data.startswith("edit_reset_no:"))
async def service_edit_reset_cancel(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await _show_service_edit_menu(
        callback.message, email, callback.from_user.id, panel_registry  # type: ignore[arg-type]
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_limit:"))
async def service_edit_limit_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    await state.update_data(email=email)
    await state.set_state(EditServiceStates.limit_ip)
    await callback.message.edit_text(t.LIMIT_IP_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("edit_comment:"))
async def service_edit_comment_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    await state.update_data(email=email)
    await state.set_state(EditServiceStates.comment)
    await callback.message.edit_text(t.COMMENT_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.message(EditServiceStates.limit_ip)
async def service_edit_limit_input(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    try:
        limit_ip = validate_limit_ip(int((message.text or "").strip()))
    except (ValueError, InvalidEditInputError) as e:
        await message.answer(str(e) if isinstance(e, InvalidEditInputError) else t.INVALID_INPUT)
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, message.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.update_service_limit_ip(ctx.reseller, email, limit_ip)
            except XuiError as e:
                await message.answer(str(e))
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return
    await message.answer(
        t.LIMIT_IP_UPDATED.format(limit_ip_label=format_limit_ip_label(limit_ip))
    )


@router.message(EditServiceStates.comment)
async def service_edit_comment_input(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    try:
        comment = validate_comment(message.text or "")
    except InvalidEditInputError as e:
        await message.answer(str(e))
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, message.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.update_service_comment(ctx.reseller, email, comment)
            except XuiError as e:
                await message.answer(str(e))
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return
    await message.answer(t.COMMENT_UPDATED)
