import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    add_traffic_confirm_kb,
    add_traffic_volume_kb,
    client_name_kb,
    confirm_create_kb,
    create_cancel_kb,
    create_pick_panel_kb,
    delete_confirm_kb,
    expiry_mode_kb,
    reduce_traffic_confirm_kb,
    reduce_traffic_volume_kb,
    reset_traffic_confirm_kb,
    service_detail_kb,
    service_edit_kb,
    SERVICES_PAGE_SIZE,
    service_list_kb,
    template_picker_kb,
    vless_qr_kb,
)
from bot.states import (
    AddTrafficStates,
    CreateServiceStates,
    EditServiceStates,
    ExtendExpiryStates,
    ReduceTrafficStates,
)
from bot.texts import fa as t
from bot.utils.edit_service import (
    InvalidEditInputError,
    format_limit_ip_label,
    validate_limit_ip,
    validate_comment,
)
from bot.utils.expiry import InvalidExpiryInputError, parse_expiry_date
from bot.utils.format_delivery import (
    DELIVERY_PARSE_MODE,
    config_display_label,
    format_delivery_message,
)
from bot.utils.qr_vless import InvalidVlessQrError, generate_vless_qr_png
from bot.utils.format_traffic import (
    client_traffic_used_bytes,
    format_bytes,
    format_expiry,
    format_traffic_message,
    normalize_traffic_data,
)
from db.repository import (
    ClientRepository,
    PanelRepository,
    ResellerPanelRepository,
    ResellerRepository,
    ServiceTemplateRepository,
    resolve_attach_inbound_ids_for_assignment,
)
from bot.utils.reseller_welcome import accessible_panel_ids, format_reseller_welcome
from db.session import get_session_factory
from services.client_volume import MIN_CLIENT_VOLUME_GB, validate_client_volume_gb
from services.quota import QuotaExceeded, QuotaService
from services.reseller_labels import (
    InvalidClientSuffixError,
    build_client_email,
    email_prefix,
    normalize_client_suffix,
)
from services.panel_registry import PanelRegistry
from services.reseller_service import (
    DeleteServiceResult,
    ResellerService,
    is_quota_refund_eligible,
)
from bot.utils.service_resolve import (
    answer_resolve_callback,
    answer_resolve_message,
    list_accessible_clients,
    open_service_context,
)
from bot.utils.panel_access import answer_panel_unavailable
from services.panel_resolve import (
    ResellerPanelUnavailableError,
    ServiceNotFoundError,
    ServicePanelUnavailableError,
    xui_for_reseller_panel,
)
from xui.client import XuiClient, XuiError, bytes_to_gb

router = Router()


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
    reseller, _ = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await message.answer(t.NOT_RESELLER)
        return
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(message.from_user.id)
        if not reseller:
            await message.answer(t.NOT_RESELLER)
            return
        welcome = await format_reseller_welcome(session, reseller)
    await message.answer(welcome)


async def _create_panel_options(
    session, reseller, panel_registry: PanelRegistry
) -> list[tuple[int, str, float]]:
    panel_repo = PanelRepository(session)
    quota_svc = QuotaService(
        ResellerRepository(session), ResellerPanelRepository(session)
    )
    global_st = await quota_svc.global_status(reseller)
    remaining = global_st.remaining_gb
    out: list[tuple[int, str, float]] = []
    for panel_id in await accessible_panel_ids(panel_registry, session, reseller):
        panel = await panel_repo.get(panel_id)
        name = panel.name if panel else f"#{panel_id}"
        out.append((panel_id, name, remaining))
    return out


async def _continue_create_flow(
    target: Message,
    state: FSMContext,
    *,
    panel_id: int,
    has_templates: bool,
) -> None:
    await state.update_data(panel_id=panel_id)
    if has_templates:
        async with get_session_factory()() as session:
            templates = await ServiceTemplateRepository(session).list_active()
        await target.answer(
            t.CREATE_PICK_TEMPLATE,
            reply_markup=template_picker_kb(templates),
        )
        return
    await state.set_state(CreateServiceStates.volume)
    await target.answer(t.CREATE_VOLUME_PROMPT, reply_markup=create_cancel_kb())


async def _prompt_pick_panel_or_continue(
    target: Message,
    state: FSMContext,
    reseller,
    panel_registry: PanelRegistry,
) -> None:
    async with get_session_factory()() as session:
        options = await _create_panel_options(session, reseller, panel_registry)
        templates = await ServiceTemplateRepository(session).list_active()
    if not options:
        await target.answer(t.NO_PANEL_ACCESS)
        return
    if len(options) == 1:
        await _continue_create_flow(
            target, state, panel_id=options[0][0], has_templates=bool(templates)
        )
        return
    await state.set_state(CreateServiceStates.pick_panel)
    await target.answer(
        t.CREATE_PICK_PANEL,
        reply_markup=create_pick_panel_kb(options),
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
async def start_create(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    reseller, _ = await _get_active_reseller(message.from_user.id)
    if not reseller:
        await message.answer(t.NOT_RESELLER)
        return
    await state.clear()
    await _prompt_pick_panel_or_continue(message, state, reseller, panel_registry)


@router.callback_query(F.data == "create:manual")
async def create_manual(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user:
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    data = await state.get_data()
    panel_id = data.get("panel_id")
    if panel_id is None:
        await state.clear()
        if callback.message:
            await _prompt_pick_panel_or_continue(
                callback.message, state, reseller, panel_registry  # type: ignore[arg-type]
            )
        await callback.answer()
        return
    await state.set_state(CreateServiceStates.volume)
    await state.update_data(panel_id=int(panel_id), template_name=None)
    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.CREATE_VOLUME_PROMPT,
            reply_markup=create_cancel_kb(),
        )
    await callback.answer()


@router.callback_query(CreateServiceStates.pick_panel, F.data.startswith("create:panel:"))
async def create_pick_panel(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        panel_id = int((callback.data or "").split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    async with get_session_factory()() as session:
        accessible = await accessible_panel_ids(panel_registry, session, reseller)
        if panel_id not in accessible:
            await callback.answer(t.NO_PANEL_ACCESS, show_alert=True)
            return
        templates = await ServiceTemplateRepository(session).list_active()
    await _continue_create_flow(
        callback.message,  # type: ignore[arg-type]
        state,
        panel_id=panel_id,
        has_templates=bool(templates),
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def create_from_template(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user:
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    data = await state.get_data()
    panel_id = data.get("panel_id")
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
    if tpl.volume_gb < MIN_CLIENT_VOLUME_GB:
        await callback.answer(t.CREATE_VOLUME_TOO_LOW, show_alert=True)
        return

    if panel_id is None:
        await state.clear()
        if callback.message:
            await _prompt_pick_panel_or_continue(
                callback.message, state, reseller, panel_registry  # type: ignore[arg-type]
            )
        await callback.answer()
        return
    await state.update_data(
        panel_id=int(panel_id),
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
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    if volume <= 0:
        await message.answer(t.INVALID_INPUT)
        return
    try:
        validate_client_volume_gb(volume)
    except ValueError:
        await message.answer(t.CREATE_VOLUME_TOO_LOW)
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

    panel_id = data.get("panel_id")
    if panel_id is None:
        await message.answer(t.INVALID_INPUT)
        return False

    async with get_session_factory()() as session:
        assignment = await ResellerPanelRepository(session).get(
            reseller.telegram_id, int(panel_id)
        )
        if not assignment:
            await message.answer(t.NO_PANEL_ACCESS)
            return False
        if await ClientRepository(session).email_exists(
            email_preview, panel_id=int(panel_id)
        ):
            await message.answer(t.EMAIL_TAKEN)
            await state.set_state(CreateServiceStates.client_name)
            return False

    inbounds = resolve_attach_inbound_ids_for_assignment(assignment)
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
    panel_registry: PanelRegistry,
    xui: XuiClient | None = None,
) -> None:
    if not callback.from_user:
        return
    if not rate_limit_check(callback.from_user.id, get_settings().create_rate_limit):
        await callback.answer(t.RATE_LIMITED, show_alert=True)
        return

    data = await state.get_data()
    if data.get("create_locked"):
        await callback.answer("در حال ساخت سرویس…", show_alert=True)
        return

    volume_gb = data.get("volume_gb")
    expiry_days = data.get("expiry_days", 0)
    client_suffix = data.get("client_suffix")
    panel_id = data.get("panel_id")
    if volume_gb is None or not client_suffix or panel_id is None:
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

        try:
            xui_client = xui or await xui_for_reseller_panel(
                panel_registry, session, reseller, int(panel_id)
            )
        except ResellerPanelUnavailableError as e:
            await state.update_data(create_locked=False)
            await answer_panel_unavailable(callback, e)
            return

        svc = ResellerService(session, xui_client)
        try:
            record, delivery = await svc.create_service(
                reseller,
                volume_gb=volume_gb,
                expiry_days=expiry_days,
                client_suffix=client_suffix,
                panel_id=int(panel_id),
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


def _format_service_list_text(total: int, page: int) -> str:
    start = page * SERVICES_PAGE_SIZE + 1
    end = min((page + 1) * SERVICES_PAGE_SIZE, total)
    header = t.SERVICE_LIST_HEADER.format(start=start, end=end, total=total)
    return f"{header}\nیکی را انتخاب کنید:"


async def _show_service_list(
    message: Message,
    emails: list[str],
    page: int = 0,
    *,
    edit: bool = False,
) -> None:
    text = _format_service_list_text(len(emails), page)
    markup = service_list_kb(emails, page=page)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


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
    await _show_service_list(message, emails, page=0)


@router.callback_query(F.data == "svc:back")
async def services_back(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    async with get_session_factory()() as session:
        emails = await _accessible_service_emails(
            session, panel_registry, callback.from_user.id
        )
    if not emails:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
    else:
        await _show_service_list(
            callback.message, emails, page=0, edit=True  # type: ignore[arg-type]
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^svc:pg:\d+$"))
async def services_page(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        page = int((callback.data or "").split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    async with get_session_factory()() as session:
        emails = await _accessible_service_emails(
            session, panel_registry, callback.from_user.id
        )
    if not emails:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
        await callback.answer()
        return
    await _show_service_list(
        callback.message, emails, page=page, edit=True  # type: ignore[arg-type]
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
    if email == "back" or email.startswith("pg:"):
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


async def _show_add_traffic_confirm(
    message: Message,
    state: FSMContext,
    *,
    user_id: int,
    email: str,
    volume_gb: float,
    panel_registry: PanelRegistry,
    edit: bool = True,
) -> bool:
    try:
        async with open_service_context(
            panel_registry, user_id, email
        ) as (ctx, session):
            quota = QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            )
            st = await quota.status(ctx.reseller, ctx.record.panel_id)
            current_gb = bytes_to_gb(ctx.record.allocated_bytes)
            remaining_before = st.remaining_gb
            if volume_gb > remaining_before:
                await message.answer(
                    f"حجم درخواستی ({volume_gb} GB) بیشتر از باقی‌مانده "
                    f"({remaining_before} GB) است."
                )
                return False
            text = t.ADD_TRAFFIC_CONFIRM.format(
                email=email,
                add_gb=volume_gb,
                current_gb=current_gb,
                new_gb=current_gb + volume_gb,
                remaining_before_gb=remaining_before,
                remaining_after_gb=remaining_before - volume_gb,
            )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return False
    await state.update_data(email=email, volume_gb=volume_gb)
    await state.set_state(AddTrafficStates.confirm)
    if edit:
        await message.edit_text(
            text, parse_mode="Markdown", reply_markup=add_traffic_confirm_kb(email)
        )
    else:
        await message.answer(
            text, parse_mode="Markdown", reply_markup=add_traffic_confirm_kb(email)
        )
    return True


@router.callback_query(F.data.regexp(r"^traf:[^:]+$"))
async def add_traffic_menu(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(email=email)
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            quota = QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            )
            st = await quota.status(ctx.reseller, ctx.record.panel_id)
            current_gb = bytes_to_gb(ctx.record.allocated_bytes)
            text = t.ADD_TRAFFIC_CHOOSE.format(
                email=email,
                current_gb=current_gb,
                remaining_gb=st.remaining_gb,
            )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode="Markdown",
        reply_markup=add_traffic_volume_kb(email),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("traf_vol:"))
async def add_traffic_quick_volume(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        volume_gb = float((callback.data or "").split(":", 1)[1])
        if volume_gb <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    ok = await _show_add_traffic_confirm(
        callback.message,  # type: ignore[arg-type]
        state,
        user_id=callback.from_user.id,
        email=email,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
    )
    if ok:
        await callback.answer()


@router.callback_query(F.data == "traf_custom")
async def add_traffic_custom_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    data = await state.get_data()
    if not data.get("email"):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.set_state(AddTrafficStates.volume)
    await callback.message.edit_text(t.ADD_TRAFFIC_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.message(AddTrafficStates.volume)
async def add_traffic_custom_volume(
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
        volume_gb = float((message.text or "").replace(",", "."))
        if volume_gb <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await _show_add_traffic_confirm(
        message,
        state,
        user_id=message.from_user.id,
        email=email,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
        edit=False,
    )


@router.callback_query(F.data == "traf_confirm")
async def add_traffic_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    email = data.get("email")
    volume_gb = data.get("volume_gb")
    if not email or volume_gb is None:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                result = await svc.add_service_traffic(
                    ctx.reseller, email, float(volume_gb)
                )
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.ADD_TRAFFIC_OK.format(
            new_total_gb=bytes_to_gb(result.new_total_bytes),
            remaining_gb=bytes_to_gb(result.remaining_bytes),
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("traf_cancel:"))
async def add_traffic_cancel(
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


async def _show_reduce_traffic_confirm(
    message: Message,
    state: FSMContext,
    *,
    user_id: int,
    email: str,
    volume_gb: float,
    panel_registry: PanelRegistry,
    edit: bool = True,
) -> bool:
    try:
        async with open_service_context(
            panel_registry, user_id, email
        ) as (ctx, session):
            quota = QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            )
            st = await quota.status(ctx.reseller, ctx.record.panel_id)
            current_gb = bytes_to_gb(ctx.record.allocated_bytes)
            remaining_before = st.remaining_gb
            traffic = await ctx.xui.get_traffic(email)
            used_gb = bytes_to_gb(client_traffic_used_bytes(traffic))
            if volume_gb > current_gb:
                await message.answer(
                    f"حجم درخواستی ({volume_gb} GB) بیشتر از سقف فعلی "
                    f"({current_gb} GB) است."
                )
                return False
            new_gb = current_gb - volume_gb
            if new_gb < used_gb:
                await message.answer(
                    f"سقف جدید ({new_gb} GB) کمتر از مصرف فعلی ({used_gb} GB) است."
                )
                return False
            text = t.REDUCE_TRAFFIC_CONFIRM.format(
                email=email,
                remove_gb=volume_gb,
                current_gb=current_gb,
                new_gb=new_gb,
                used_gb=used_gb,
                remaining_before_gb=remaining_before,
                remaining_after_gb=remaining_before + volume_gb,
            )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return False
    except XuiError as e:
        await message.answer(str(e))
        return False
    await state.update_data(email=email, volume_gb=volume_gb)
    await state.set_state(ReduceTrafficStates.confirm)
    if edit:
        await message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=reduce_traffic_confirm_kb(email),
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=reduce_traffic_confirm_kb(email),
        )
    return True


@router.callback_query(F.data.regexp(r"^trafd:[^:]+$"))
async def reduce_traffic_menu(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    email = (callback.data or "").split(":", 1)[1]
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(email=email)
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            quota = QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            )
            st = await quota.status(ctx.reseller, ctx.record.panel_id)
            current_gb = bytes_to_gb(ctx.record.allocated_bytes)
            traffic = await ctx.xui.get_traffic(email)
            used_gb = bytes_to_gb(client_traffic_used_bytes(traffic))
            text = t.REDUCE_TRAFFIC_CHOOSE.format(
                email=email,
                current_gb=current_gb,
                used_gb=used_gb,
                remaining_gb=st.remaining_gb,
            )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    except XuiError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode="Markdown",
        reply_markup=reduce_traffic_volume_kb(email),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trafd_vol:"))
async def reduce_traffic_quick_volume(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        volume_gb = float((callback.data or "").split(":", 1)[1])
        if volume_gb <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    data = await state.get_data()
    email = data.get("email")
    if not email:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    ok = await _show_reduce_traffic_confirm(
        callback.message,  # type: ignore[arg-type]
        state,
        user_id=callback.from_user.id,
        email=email,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
    )
    if ok:
        await callback.answer()


@router.callback_query(F.data == "trafd_custom")
async def reduce_traffic_custom_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    data = await state.get_data()
    if not data.get("email"):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.set_state(ReduceTrafficStates.volume)
    await callback.message.edit_text(t.REDUCE_TRAFFIC_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.message(ReduceTrafficStates.volume)
async def reduce_traffic_custom_volume(
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
        volume_gb = float((message.text or "").replace(",", "."))
        if volume_gb <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await _show_reduce_traffic_confirm(
        message,
        state,
        user_id=message.from_user.id,
        email=email,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
        edit=False,
    )


@router.callback_query(F.data == "trafd_confirm")
async def reduce_traffic_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    email = data.get("email")
    volume_gb = data.get("volume_gb")
    if not email or volume_gb is None:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                result = await svc.remove_service_traffic(
                    ctx.reseller, email, float(volume_gb)
                )
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.REDUCE_TRAFFIC_OK.format(
            new_total_gb=bytes_to_gb(result.new_total_bytes),
            remaining_gb=bytes_to_gb(result.remaining_bytes),
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trafd_cancel:"))
async def reduce_traffic_cancel(
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


def _qr_caption(email: str, remark: str) -> str:
    label = config_display_label(email, remark)
    remark_line = f"{label}\n" if label else ""
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
        caption=_qr_caption(email, cfg.remark),
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
async def service_delete_prompt(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
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

    settings = get_settings()
    threshold_gb = settings.quota_refund_max_traffic_gb
    refund_hint = t.DELETE_CONFIRM_REFUND_UNKNOWN
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            traffic = await svc.get_traffic(ctx.reseller, email)
            used = client_traffic_used_bytes(traffic)
            used_s = format_bytes(used)
            if is_quota_refund_eligible(used, max_traffic_gb=threshold_gb):
                refund_hint = t.DELETE_CONFIRM_REFUND_YES.format(used=used_s)
            else:
                refund_hint = t.DELETE_CONFIRM_REFUND_NO.format(
                    used=used_s, threshold_gb=threshold_gb
                )
    except (ServiceNotFoundError, ServicePanelUnavailableError, XuiError):
        pass

    await callback.message.edit_text(  # type: ignore[union-attr]
        t.DELETE_CONFIRM.format(
            email=email,
            refund_hint=refund_hint,
            threshold_gb=threshold_gb,
        ),
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
    result = DeleteServiceResult(refunded_bytes=0)
    try:
        async with open_service_context(
            panel_registry, callback.from_user.id, email
        ) as (ctx, session):
            svc = ResellerService(session, ctx.xui)
            try:
                result = await svc.delete_service(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    if result.refunded_bytes > 0:
        deleted_text = t.SERVICE_DELETED_QUOTA_REFUNDED.format(
            refund_gb=bytes_to_gb(result.refunded_bytes)
        )
    else:
        deleted_text = t.SERVICE_DELETED
    await callback.message.edit_text(deleted_text)  # type: ignore[union-attr]
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
