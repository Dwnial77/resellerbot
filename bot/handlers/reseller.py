import logging
import secrets
from dataclasses import dataclass

import httpx

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
    renew_cancel_kb,
    renew_confirm_kb,
    renew_source_kb,
    service_detail_kb,
    service_edit_kb,
    service_search_cancel_kb,
    SERVICES_PAGE_SIZE,
    service_list_kb,
    sub_regen_confirm_kb,
    template_picker_kb,
)
from bot.states import (
    AddTrafficStates,
    CreateServiceStates,
    EditServiceStates,
    ExtendExpiryStates,
    ReduceTrafficStates,
    RenewServiceStates,
    SearchServiceStates,
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
    format_delivery_message,
)
from bot.utils.qr_vless import InvalidVlessQrError, generate_qr_png
from bot.utils.format_traffic import (
    EXPIRY_EXPIRED,
    EXPIRY_SOON,
    client_traffic_used_bytes,
    expiry_status,
    service_status,
    traffic_status,
    progress_bar,
    format_bytes,
    format_expiry,
    format_traffic_message,
    normalize_traffic_data,
)
from db.models import ClientRecord
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
from services.quota import QuotaExceeded, QuotaService, plan_remove_traffic
from services.reseller_labels import (
    InvalidClientSuffixError,
    build_client_email,
    email_prefix,
    normalize_client_suffix,
)
from services.panel_registry import PanelNotFoundError, PanelRegistry
from services.reseller_service import (
    DeleteServiceResult,
    ResellerService,
    panel_expiry_ms,
    refund_block_reason,
)
from bot.utils.service_resolve import (
    answer_resolve_callback,
    answer_resolve_message,
    list_accessible_clients,
    open_service_context_by_id,
)
from bot.utils.panel_access import answer_panel_unavailable
from services.panel_resolve import (
    ResellerPanelUnavailableError,
    ServiceNotFoundError,
    ServicePanelUnavailableError,
    xui_for_reseller_panel,
)
from xui.client import XuiError, bytes_to_gb, gb_to_bytes

logger = logging.getLogger(__name__)
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


async def _send_delivery_with_qr(
    message: Message,
    email: str,
    delivery,
    *,
    created: bool,
    sub_public_url_configured: bool,
) -> bool:
    """Send the links text plus a single QR — the sub link, or the first config."""
    await message.answer(
        format_delivery_message(
            email,
            delivery,
            created=created,
            sub_public_url_configured=sub_public_url_configured,
        ),
        parse_mode=DELIVERY_PARSE_MODE,
    )
    if delivery.subscription_links:
        payload = delivery.subscription_links[0]
        caption = t.SUB_QR_CAPTION.format(email=email)
        filename = "sub-qr.png"
    elif delivery.vless_configs:
        payload = delivery.vless_configs[0].link
        caption = t.CONFIG_QR_CAPTION.format(email=email)
        filename = "vless-qr.png"
    else:
        return False
    try:
        png = generate_qr_png(payload)
    except InvalidVlessQrError:
        return False
    await message.answer_photo(
        BufferedInputFile(png, filename=filename),
        caption=caption,
    )
    return True


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

        # Always resolve by the picked panel — the middleware-injected `xui` is
        # the reseller's *default* panel and would misroute multi-panel creates.
        try:
            xui_client = await xui_for_reseller_panel(
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
    try:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        pass
    await _send_delivery_with_qr(
        callback.message,  # type: ignore[arg-type]
        record.email,
        delivery,
        created=True,
        sub_public_url_configured=bool(xui_client.sub_public_url),
    )
    await callback.answer()


@router.callback_query(F.data == "create:confirm")
async def confirm_create_stale(callback: CallbackQuery) -> None:
    await callback.answer(
        "این دکمه منقضی شده. از «ساخت سرویس» دوباره شروع کنید.",
        show_alert=True,
    )


MAX_SEARCH_QUERY_LEN = 40


# Problem services first — the whole point of the icons is spotting them fast.
_STATUS_SORT_RANK = {EXPIRY_EXPIRED: 0, EXPIRY_SOON: 1}


async def _service_usage(
    registry: PanelRegistry, records: list[ClientRecord]
) -> dict[int, tuple[int, int]]:
    """`record.id -> (used, total)`, one panel request per panel — not per service.

    Fetching usage per client is what made the alert loop overwhelm the panel,
    so this groups by panel first. A panel that fails is simply left out: those
    services fall back to time-only status instead of breaking the whole list.
    """
    by_panel: dict[int, list[ClientRecord]] = {}
    for record in records:
        by_panel.setdefault(record.panel_id, []).append(record)

    usage: dict[int, tuple[int, int]] = {}
    for panel_id, panel_records in by_panel.items():
        try:
            panel_usage = await registry.get_client(panel_id).client_usage_map()
        except (PanelNotFoundError, XuiError, httpx.HTTPError) as e:
            logger.warning("Usage unavailable for panel #%s: %r", panel_id, e)
            continue
        if panel_usage is None:
            continue
        for record in panel_records:
            row = panel_usage.get(record.email)
            if row is None:
                continue
            used, panel_total = row
            # total == 0 on the panel means unlimited there, so fall back to
            # the volume we allocated; only both being zero is truly unlimited.
            total = panel_total if panel_total > 0 else int(record.allocated_bytes or 0)
            usage[record.id] = (used, total)
    return usage


def _record_status(record: ClientRecord, usage: dict[int, tuple[int, int]]) -> str:
    used, total = usage.get(record.id, (None, 0))
    return service_status(int(record.expiry_time or 0), used, total)


async def _accessible_service_records(
    session, registry: PanelRegistry, reseller_tg_id: int
) -> tuple[list[ClientRecord], dict[int, tuple[int, int]]]:
    clients = await list_accessible_clients(session, registry, reseller_tg_id)
    usage = await _service_usage(registry, clients)
    ordered = sorted(
        clients,
        key=lambda c: _STATUS_SORT_RANK.get(_record_status(c, usage), 2),
    )
    return ordered, usage


def _normalize_search_query(raw: str) -> str:
    return (raw or "").strip()[:MAX_SEARCH_QUERY_LEN]


def _filter_records(
    records: list[ClientRecord], query: str | None
) -> list[ClientRecord]:
    q = (query or "").strip().lower()
    if not q:
        return records
    return [r for r in records if q in r.email.lower()]


def _format_service_list_text(
    records: list[ClientRecord],
    page: int,
    query: str | None = None,
    usage: dict[int, tuple[int, int]] | None = None,
) -> str:
    total = len(records)
    start = page * SERVICES_PAGE_SIZE + 1 if total else 0
    end = min((page + 1) * SERVICES_PAGE_SIZE, total)
    if query:
        header = t.SERVICE_SEARCH_HEADER.format(
            query=query, start=start, end=end, total=total
        )
    else:
        header = t.SERVICE_LIST_HEADER.format(start=start, end=end, total=total)

    # Counts go here, not on the buttons: this text is multi-line, so each
    # number sits on its own "label: value" line and bidi can't reorder them.
    statuses = [_record_status(r, usage or {}) for r in records]
    lines = [header]
    expired = statuses.count(EXPIRY_EXPIRED)
    soon = statuses.count(EXPIRY_SOON)
    if expired:
        lines.append(t.SERVICE_LIST_EXPIRED_COUNT.format(count=expired))
    if soon:
        lines.append(t.SERVICE_LIST_SOON_COUNT.format(count=soon))
    lines.append(t.SERVICE_LIST_PICK)
    return "\n".join(lines)


async def _show_service_list(
    message: Message,
    records: list[ClientRecord],
    page: int = 0,
    *,
    query: str | None = None,
    edit: bool = False,
    usage: dict[int, tuple[int, int]] | None = None,
) -> None:
    if query and not records:
        markup = service_list_kb([], page=0, query=query)
        text = t.SEARCH_NO_RESULTS.format(query=query)
        if edit:
            await message.edit_text(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup)
        return
    text = _format_service_list_text(records, page, query, usage)
    markup = service_list_kb(records, page=page, query=query, usage=usage)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.message(F.text == btn.MY_SERVICES)
async def my_services(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(message.from_user.id)
        if not reseller or not reseller.is_active:
            await message.answer(t.NOT_RESELLER)
            return
        records, usage = await _accessible_service_records(
            session, panel_registry, message.from_user.id
        )

    if not records:
        await message.answer(t.NO_ACCESSIBLE_SERVICES)
        return
    data = await state.get_data()
    query = data.get("service_search_query")
    await _show_service_list(
        message, _filter_records(records, query), page=0, query=query, usage=usage
    )


@router.callback_query(F.data == "svc:back")
async def services_back(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    async with get_session_factory()() as session:
        records, usage = await _accessible_service_records(
            session, panel_registry, callback.from_user.id
        )
    if not records:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
    else:
        data = await state.get_data()
        query = data.get("service_search_query")
        await _show_service_list(
            callback.message,  # type: ignore[arg-type]
            _filter_records(records, query),
            page=0,
            query=query,
            edit=True,
            usage=usage,
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^svc:pg:\d+$"))
async def services_page(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
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
        records, usage = await _accessible_service_records(
            session, panel_registry, callback.from_user.id
        )
    if not records:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
        await callback.answer()
        return
    data = await state.get_data()
    query = data.get("service_search_query")
    await _show_service_list(
        callback.message,  # type: ignore[arg-type]
        _filter_records(records, query),
        page=page,
        query=query,
        edit=True,
        usage=usage,
    )
    await callback.answer()


@router.callback_query(F.data == "svc:search")
async def service_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(SearchServiceStates.query)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.SEARCH_SERVICE_PROMPT,
        reply_markup=service_search_cancel_kb(),
    )
    await callback.answer()


@router.message(SearchServiceStates.query)
async def service_search_input(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    query = _normalize_search_query(message.text or "")
    if not query:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(service_search_query=query)
    await state.set_state(None)
    async with get_session_factory()() as session:
        records, usage = await _accessible_service_records(
            session, panel_registry, message.from_user.id
        )
    await _show_service_list(
        message, _filter_records(records, query), page=0, query=query, usage=usage
    )


@router.callback_query(F.data == "svc:search:clear")
async def service_search_clear(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.update_data(service_search_query=None)
    async with get_session_factory()() as session:
        records, usage = await _accessible_service_records(
            session, panel_registry, callback.from_user.id
        )
    if not records:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
    else:
        await _show_service_list(
            callback.message,  # type: ignore[arg-type]
            records,
            page=0,
            query=None,
            edit=True,
            usage=usage,
        )
    await callback.answer()


@router.callback_query(F.data == "svc:search:cancel")
async def service_search_cancel(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.set_state(None)
    async with get_session_factory()() as session:
        records, usage = await _accessible_service_records(
            session, panel_registry, callback.from_user.id
        )
    data = await state.get_data()
    query = data.get("service_search_query")
    if not records:
        await callback.message.edit_text(t.NO_ACCESSIBLE_SERVICES)  # type: ignore[union-attr]
    else:
        await _show_service_list(
            callback.message,  # type: ignore[arg-type]
            _filter_records(records, query),
            page=0,
            query=query,
            edit=True,
            usage=usage,
        )
    await callback.answer()


def _record_id_from(callback: CallbackQuery) -> int | None:
    """Parse the trailing service record id out of `prefix:<id>` callback data."""
    raw = (callback.data or "").split(":", 1)
    if len(raw) != 2:
        return None
    try:
        return int(raw[1])
    except ValueError:
        return None


async def _service_email(user_id: int, record_id: int) -> str | None:
    """Owner-checked email lookup for display-only prompts (no panel call)."""
    async with get_session_factory()() as session:
        record = await ClientRepository(session).get_for_reseller_id(
            user_id, record_id
        )
    return record.email if record else None


@dataclass
class ServiceDetail:
    email: str
    enabled: bool
    expiry_ms: int
    used_bytes: int | None
    total_bytes: int


def _service_detail_text(detail: ServiceDetail) -> str:
    status = "فعال" if detail.enabled else "غیرفعال"
    lines = [
        f"سرویس: `{detail.email}`",
        f"وضعیت: {status}",
    ]
    # One "label: value" per line — never several numeric runs on one RTL line
    # (see commit 0d9632d).
    if detail.used_bytes is None:
        lines.append("مصرف: نامشخص")
    elif detail.total_bytes > 0:
        lines.append(
            f"مصرف: {format_bytes(detail.used_bytes)} از "
            f"{format_bytes(detail.total_bytes)}"
        )
        bar, percent = progress_bar(detail.used_bytes, detail.total_bytes)
        lines.append(f"[{bar}] {percent}%")
    else:
        lines.append(f"مصرف: {format_bytes(detail.used_bytes)} (سقف نامحدود)")
    lines.append(f"انقضا: {format_expiry(detail.expiry_ms)}")

    # The list shows one icon for both causes, so name the cause here.
    note = _service_status_note(detail)
    if note:
        lines.append(note)
    return "\n".join(lines)


def _service_status_note(detail: ServiceDetail) -> str:
    volume = traffic_status(detail.used_bytes, detail.total_bytes)
    time_left = expiry_status(detail.expiry_ms)
    if volume == EXPIRY_EXPIRED:
        return t.SERVICE_NOTE_VOLUME_GONE
    if time_left == EXPIRY_EXPIRED:
        return t.SERVICE_NOTE_TIME_GONE
    if volume == EXPIRY_SOON:
        return t.SERVICE_NOTE_VOLUME_LOW
    if time_left == EXPIRY_SOON:
        return t.SERVICE_NOTE_TIME_LOW
    return ""


async def _load_service_detail(
    user_id: int, record_id: int, registry: PanelRegistry
) -> ServiceDetail:
    enabled = True
    used_bytes: int | None = None
    async with open_service_context_by_id(registry, user_id, record_id) as (ctx, session):
        email = ctx.record.email
        expiry_ms = int(ctx.record.expiry_time or 0)
        total_bytes = int(ctx.record.allocated_bytes or 0)
        svc = ResellerService(session, ctx.xui)
        try:
            traffic = await svc.get_traffic(ctx.reseller, email)
            data = normalize_traffic_data(traffic)
            enabled = bool(data.get("enable", True))
            used_bytes = client_traffic_used_bytes(data)
            try:
                panel_total = int(data.get("total") or 0)
                if panel_total > 0:
                    total_bytes = panel_total
            except (TypeError, ValueError):
                pass
            raw_exp = data.get("expiryTime", data.get("expiry_time", 0))
            try:
                panel_exp = int(raw_exp or 0)
                if panel_exp > 0:
                    expiry_ms = panel_exp
            except (TypeError, ValueError):
                pass
        except XuiError:
            pass
    return ServiceDetail(
        email=email,
        enabled=enabled,
        expiry_ms=expiry_ms,
        used_bytes=used_bytes,
        total_bytes=total_bytes,
    )


async def _show_service_detail(
    message: Message,
    record_id: int,
    user_id: int,
    registry: PanelRegistry,
    *,
    send_new: bool = False,
) -> None:
    """Render the detail view, either in place or as a fresh message."""
    detail = await _load_service_detail(user_id, record_id, registry)
    show = message.answer if send_new else message.edit_text
    await show(
        _service_detail_text(detail),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(record_id, enabled=detail.enabled),
    )


# Numeric-only so `svc:back`, `svc:pg:2` and `svc:search` fall through to their
# own handlers instead of needing an in-body guard.
@router.callback_query(F.data.regexp(r"^svc:\d+$"))
async def service_detail(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        detail = await _load_service_detail(
            callback.from_user.id, record_id, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        _service_detail_text(detail),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(record_id, enabled=detail.enabled),
    )
    await callback.answer()


async def _show_renew_source(
    message: Message, record_id: int, user_id: int, registry: PanelRegistry
) -> bool:
    """Show the renew template picker; returns False if the service can't be opened."""
    async with open_service_context_by_id(registry, user_id, record_id) as (ctx, session):
        email = ctx.record.email
        quota_svc = QuotaService(
            ResellerRepository(session), ResellerPanelRepository(session)
        )
        st = await quota_svc.global_status(ctx.reseller)
        current_gb = bytes_to_gb(ctx.record.allocated_bytes)
        expiry_ms = int(ctx.record.expiry_time or 0)
        templates = await ServiceTemplateRepository(session).list_active()
    await message.edit_text(
        t.RENEW_CHOOSE_SOURCE.format(
            email=email,
            current_gb=current_gb,
            expiry_label=format_expiry(expiry_ms),
            remaining_gb=st.remaining_gb,
        ),
        parse_mode="Markdown",
        reply_markup=renew_source_kb(templates),
    )
    return True


@router.callback_query(F.data.startswith("renew:"))
async def renew_start(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    try:
        await _show_renew_source(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await state.set_state(RenewServiceStates.pick_source)
    await state.update_data(record_id=record_id)
    await callback.answer()


async def _show_renew_confirm(
    message: Message, state: FSMContext, user_id: int, registry: PanelRegistry
) -> None:
    data = await state.get_data()
    record_id = data.get("record_id")
    volume_gb = data.get("volume_gb")
    expiry_days = int(data.get("expiry_days", 0))
    if record_id is None or volume_gb is None:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    async with open_service_context_by_id(registry, user_id, record_id) as (ctx, session):
        email = ctx.record.email
        quota_svc = QuotaService(
            ResellerRepository(session), ResellerPanelRepository(session)
        )
        st = await quota_svc.global_status(ctx.reseller)
    charge = gb_to_bytes(volume_gb)
    template_name = data.get("template_name")
    await state.set_state(RenewServiceStates.confirm)
    await message.answer(
        t.RENEW_CONFIRM.format(
            email=email,
            template_line=f"قالب: {template_name}\n" if template_name else "",
            volume_gb=volume_gb,
            expiry_label=f"{expiry_days} روز" if expiry_days > 0 else "نامحدود",
            remaining_before_gb=st.remaining_gb,
            remaining_after_gb=bytes_to_gb(max(0, st.remaining_bytes - charge)),
        ),
        parse_mode="Markdown",
        reply_markup=renew_confirm_kb(),
    )


@router.callback_query(RenewServiceStates.pick_source, F.data.startswith("rtpl:"))
async def renew_pick_template(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
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
    if tpl.volume_gb < MIN_CLIENT_VOLUME_GB:
        await callback.answer(t.CREATE_VOLUME_TOO_LOW, show_alert=True)
        return
    await state.update_data(
        volume_gb=tpl.volume_gb,
        expiry_days=tpl.expiry_days,
        template_name=tpl.name,
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        pass
    try:
        await _show_renew_confirm(
            callback.message, state, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


@router.callback_query(RenewServiceStates.pick_source, F.data == "rman")
async def renew_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.update_data(template_name=None)
    await state.set_state(RenewServiceStates.volume)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RENEW_VOLUME_PROMPT.format(min_gb=MIN_CLIENT_VOLUME_GB),
        reply_markup=renew_cancel_kb(),
    )
    await callback.answer()


@router.message(RenewServiceStates.volume)
async def renew_process_volume(message: Message, state: FSMContext) -> None:
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
    await state.set_state(RenewServiceStates.expiry)
    await message.answer(t.RENEW_EXPIRY_PROMPT, reply_markup=renew_cancel_kb())


@router.message(RenewServiceStates.expiry)
async def renew_process_expiry(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    try:
        days = int((message.text or "").strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(expiry_days=days)
    try:
        await _show_renew_confirm(
            message, state, message.from_user.id, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await state.clear()
        await answer_resolve_message(message, e)


@router.callback_query(RenewServiceStates.confirm, F.data == "rcfm")
async def renew_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    rate_limit_check,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    if not rate_limit_check(callback.from_user.id, get_settings().create_rate_limit):
        await callback.answer(t.RATE_LIMITED, show_alert=True)
        return

    data = await state.get_data()
    if data.get("renew_locked"):
        await callback.answer("در حال تمدید سرویس…", show_alert=True)
        return
    record_id = data.get("record_id")
    volume_gb = data.get("volume_gb")
    expiry_days = int(data.get("expiry_days", 0))
    if record_id is None or volume_gb is None:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    await state.update_data(renew_locked=True)
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
            svc = ResellerService(session, ctx.xui)
            try:
                result = await svc.renew_service(
                    ctx.reseller, email, volume_gb, expiry_days
                )
            except XuiError as e:
                await state.update_data(renew_locked=False)
                await callback.message.edit_text(str(e))  # type: ignore[union-attr]
                await callback.answer()
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await state.clear()
        await answer_resolve_callback(callback, e)
        return

    await state.clear()
    text = t.RENEW_OK.format(
        new_total_gb=bytes_to_gb(result.new_total_bytes),
        expiry_label=format_expiry(result.new_expiry_ms),
        remaining_gb=bytes_to_gb(result.remaining_bytes),
    )
    if result.traffic_reset_failed:
        text += t.RENEW_RESET_WARN
    await callback.message.edit_text(text)  # type: ignore[union-attr]
    try:
        await _show_service_detail(
            callback.message,  # type: ignore[arg-type]
            record_id,
            callback.from_user.id,
            panel_registry,
            send_new=True,
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


@router.callback_query(F.data.in_({"rcfm", "rman"}) | F.data.startswith("rtpl:"))
async def renew_stale(callback: CallbackQuery) -> None:
    await callback.answer(
        "این دکمه منقضی شده. از «تمدید کانفیگ» دوباره شروع کنید.",
        show_alert=True,
    )


@router.callback_query(F.data == "rcnl")
async def renew_cancel(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    record_id = data.get("record_id")
    await state.clear()
    if record_id is None:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()


@router.callback_query(F.data.regexp(r"^exp:\d+$"))
async def expiry_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        detail = await _load_service_detail(
            callback.from_user.id, record_id, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.EXPIRY_CHOOSE_MODE.format(
            email=detail.email,
            expiry_label=format_expiry(detail.expiry_ms),
        ),
        parse_mode="Markdown",
        reply_markup=expiry_mode_kb(record_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exp_add:"))
async def expiry_start_add_days(
    callback: CallbackQuery, state: FSMContext
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(record_id=record_id)
    await state.set_state(ExtendExpiryStates.add_days)
    await callback.message.edit_text(t.EXPIRY_PROMPT_ADD_DAYS)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("exp_date:"))
async def expiry_start_set_date(
    callback: CallbackQuery, state: FSMContext
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(record_id=record_id)
    await state.set_state(ExtendExpiryStates.set_date)
    await callback.message.edit_text(t.EXPIRY_PROMPT_SET_DATE)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("exp_unlim:"))
async def expiry_set_unlimited(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
        await _show_service_edit_menu(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
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
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_edit_menu(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
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
    record_id: int,
    volume_gb: float,
    panel_registry: PanelRegistry,
    edit: bool = True,
) -> bool:
    try:
        async with open_service_context_by_id(
            panel_registry, user_id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    await state.update_data(record_id=record_id, volume_gb=volume_gb)
    await state.set_state(AddTrafficStates.confirm)
    if edit:
        await message.edit_text(
            text, parse_mode="Markdown", reply_markup=add_traffic_confirm_kb(record_id)
        )
    else:
        await message.answer(
            text, parse_mode="Markdown", reply_markup=add_traffic_confirm_kb(record_id)
        )
    return True


@router.callback_query(F.data.regexp(r"^traf:\d+$"))
async def add_traffic_menu(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(record_id=record_id)
    await state.set_state(AddTrafficStates.choose)
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
        reply_markup=add_traffic_volume_kb(record_id),
    )
    await callback.answer()


@router.callback_query(AddTrafficStates.choose, F.data.startswith("traf_vol:"))
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
    record_id = data.get("record_id")
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    ok = await _show_add_traffic_confirm(
        callback.message,  # type: ignore[arg-type]
        state,
        user_id=callback.from_user.id,
        record_id=record_id,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
    )
    if ok:
        await callback.answer()


@router.callback_query(AddTrafficStates.choose, F.data == "traf_custom")
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
    record_id = data.get("record_id")
    if record_id is None:
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
        record_id=record_id,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
        edit=False,
    )


@router.callback_query(AddTrafficStates.confirm, F.data == "traf_confirm")
async def add_traffic_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    record_id = data.get("record_id")
    volume_gb = data.get("volume_gb")
    if record_id is None or volume_gb is None:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    await _show_service_edit_menu(
        callback.message,  # type: ignore[arg-type]
        record_id,
        callback.from_user.id,
        panel_registry,
        send_new=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("traf_cancel:"))
async def add_traffic_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_edit_menu(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
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
    record_id: int,
    volume_gb: float,
    panel_registry: PanelRegistry,
    edit: bool = True,
) -> bool:
    try:
        async with open_service_context_by_id(
            panel_registry, user_id, record_id
        ) as (ctx, session):
            email = ctx.record.email
            quota = QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            )
            st = await quota.status(ctx.reseller, ctx.record.panel_id)
            current_gb = bytes_to_gb(ctx.record.allocated_bytes)
            remaining_before = st.remaining_gb
            traffic = await ctx.xui.get_traffic(email)
            used_gb = bytes_to_gb(client_traffic_used_bytes(traffic))
            used_bytes = client_traffic_used_bytes(traffic)
            try:
                removed = quota.validate_remove_traffic(
                    ctx.reseller,
                    volume_gb,
                    current_allocated_bytes=ctx.record.allocated_bytes,
                    used_bytes=used_bytes,
                )
            except QuotaExceeded as e:
                await message.answer(str(e))
                return False
            plan = plan_remove_traffic(
                ctx.record.allocated_bytes, removed, used_bytes
            )
            text = t.REDUCE_TRAFFIC_CONFIRM.format(
                email=email,
                remove_gb=bytes_to_gb(plan.removed_bytes),
                current_gb=current_gb,
                new_gb=bytes_to_gb(plan.new_total_bytes),
                used_gb=used_gb,
                remaining_before_gb=remaining_before,
                remaining_after_gb=bytes_to_gb(
                    st.remaining_bytes + plan.removed_bytes
                ),
            )
            if plan.disable:
                text += t.REDUCE_TRAFFIC_DISABLE_NOTE
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return False
    except XuiError as e:
        await message.answer(str(e))
        return False
    await state.update_data(record_id=record_id, volume_gb=volume_gb)
    await state.set_state(ReduceTrafficStates.confirm)
    if edit:
        await message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=reduce_traffic_confirm_kb(record_id),
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=reduce_traffic_confirm_kb(record_id),
        )
    return True


@router.callback_query(F.data.regexp(r"^trafd:\d+$"))
async def reduce_traffic_menu(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(record_id=record_id)
    await state.set_state(ReduceTrafficStates.choose)
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
        reply_markup=reduce_traffic_volume_kb(record_id),
    )
    await callback.answer()


@router.callback_query(ReduceTrafficStates.choose, F.data.startswith("trafd_vol:"))
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
    record_id = data.get("record_id")
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    ok = await _show_reduce_traffic_confirm(
        callback.message,  # type: ignore[arg-type]
        state,
        user_id=callback.from_user.id,
        record_id=record_id,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
    )
    if ok:
        await callback.answer()


@router.callback_query(ReduceTrafficStates.choose, F.data == "trafd_custom")
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
    record_id = data.get("record_id")
    if record_id is None:
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
        record_id=record_id,
        volume_gb=volume_gb,
        panel_registry=panel_registry,
        edit=False,
    )


@router.callback_query(ReduceTrafficStates.confirm, F.data == "trafd_confirm")
async def reduce_traffic_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    record_id = data.get("record_id")
    volume_gb = data.get("volume_gb")
    if record_id is None or volume_gb is None:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    ok_text = (
        t.REDUCE_TRAFFIC_OK_DISABLED if result.disabled else t.REDUCE_TRAFFIC_OK
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        ok_text.format(
            new_total_gb=bytes_to_gb(result.new_total_bytes),
            remaining_gb=bytes_to_gb(result.remaining_bytes),
        )
    )
    await _show_service_edit_menu(
        callback.message,  # type: ignore[arg-type]
        record_id,
        callback.from_user.id,
        panel_registry,
        send_new=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trafd_cancel:"))
async def reduce_traffic_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    panel_registry: PanelRegistry,
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_edit_menu(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
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
    record_id = data.get("record_id")
    if record_id is None:
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
        async with open_service_context_by_id(
            panel_registry, message.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    await _show_service_edit_menu(
        message, record_id, message.from_user.id, panel_registry, send_new=True
    )


@router.message(ExtendExpiryStates.set_date)
async def expiry_process_set_date(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    record_id = data.get("record_id")
    if record_id is None:
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
        async with open_service_context_by_id(
            panel_registry, message.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    await _show_service_edit_menu(
        message, record_id, message.from_user.id, panel_registry, send_new=True
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
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user:
        return
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
        detail = await _load_service_detail(
            callback.from_user.id, record_id, panel_registry
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        _service_detail_text(detail),
        parse_mode="Markdown",
        reply_markup=service_detail_kb(record_id, enabled=detail.enabled),
    )
    await callback.answer(
        t.SERVICE_ENABLED if enabled else t.SERVICE_DISABLED,
    )


@router.callback_query(F.data.startswith("linkqr:"))
async def service_link_and_qr(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    sent_qr = await _send_delivery_with_qr(
        callback.message,  # type: ignore[arg-type]
        email,
        delivery,
        created=False,
        sub_public_url_configured=bool(service_xui.sub_public_url),
    )
    await callback.answer(t.QR_SENT if sent_qr else t.QR_NOT_AVAILABLE)


@router.callback_query(F.data.startswith("traffic:"))
async def service_traffic(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user:
        return
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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


@router.callback_query(F.data.regexp(r"^del:\d+$"))
async def service_delete_prompt(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    settings = get_settings()
    threshold_gb = settings.quota_refund_max_traffic_gb
    refund_hint = t.DELETE_CONFIRM_REFUND_UNKNOWN
    # Opening the context already enforces ownership, so no pre-check is needed;
    # only the panel call is allowed to fail silently.
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
            svc = ResellerService(session, ctx.xui)
            try:
                traffic = await svc.get_traffic(ctx.reseller, email)
            except XuiError:
                traffic = None
            if traffic is not None:
                used = client_traffic_used_bytes(traffic)
                used_s = format_bytes(used)
                # Same inputs the delete itself uses, so the prediction here
                # cannot disagree with what actually happens.
                reason = refund_block_reason(
                    used,
                    expiry_ms=panel_expiry_ms(traffic, ctx.record),
                    created_at=ctx.record.created_at,
                )
                if reason is None:
                    refund_hint = t.DELETE_CONFIRM_REFUND_YES.format(used=used_s)
                else:
                    refund_hint = t.DELETE_CONFIRM_REFUND_NO.format(
                        used=used_s,
                        reason=t.REFUND_BLOCK_REASONS[reason.value].format(
                            threshold_gb=f"{threshold_gb:g}",
                            max_age_hours=f"{settings.quota_refund_max_age_hours:g}",
                        ),
                    )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        t.DELETE_CONFIRM.format(
            email=email,
            refund_hint=refund_hint,
            threshold_gb=f"{threshold_gb:g}",
            max_age_hours=f"{settings.quota_refund_max_age_hours:g}",
        ),
        parse_mode="Markdown",
        reply_markup=delete_confirm_kb(record_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_confirm:"))
async def service_delete_confirm(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user:
        return
    result = DeleteServiceResult(refunded_bytes=0)
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
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
    message: Message,
    record_id: int,
    user_id: int,
    registry: PanelRegistry,
    *,
    send_new: bool = False,
) -> None:
    """Render the edit menu, either in place or as a fresh message."""
    show = message.answer if send_new else message.edit_text
    limit_ip = 0
    comment = ""
    try:
        async with open_service_context_by_id(registry, user_id, record_id) as (ctx, session):
            email = ctx.record.email
            svc = ResellerService(session, ctx.xui)
            try:
                limit_ip, comment = await svc.get_client_panel_fields(
                    ctx.reseller, email
                )
            except XuiError as e:
                await show(str(e))
                return
    except ServiceNotFoundError:
        await show(t.SERVICE_NOT_FOUND)
        return
    except ServicePanelUnavailableError as e:
        await show(t.SERVICE_PANEL_UNAVAILABLE.format(panel_id=e.panel_id))
        return
    await show(
        t.EDIT_MENU.format(
            email=email,
            limit_ip_label=format_limit_ip_label(limit_ip),
            comment_label=_comment_display(comment),
        ),
        parse_mode="Markdown",
        reply_markup=service_edit_kb(record_id),
    )


@router.callback_query(F.data.regexp(r"^edit:\d+$"))
async def service_edit_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await _show_service_edit_menu(
        callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_back:"))
async def service_edit_back(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        await _show_service_detail(
            callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
        )
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.answer()



@router.callback_query(F.data.startswith("edit_back_menu:"))
async def service_edit_back_menu(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await _show_service_edit_menu(
        callback.message, record_id, callback.from_user.id, panel_registry  # type: ignore[arg-type]
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_name:"))
async def service_rename_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    reseller, _ = await _get_active_reseller(callback.from_user.id)
    if not reseller:
        await callback.answer(t.NOT_RESELLER, show_alert=True)
        return
    email = await _service_email(callback.from_user.id, record_id)
    if email is None:
        await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
        return
    await state.update_data(record_id=record_id)
    await state.set_state(EditServiceStates.rename)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RENAME_PROMPT.format(
            email=email, prefix=f"{email_prefix(reseller)}-client-"
        ),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(EditServiceStates.rename)
async def service_rename_input(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    record_id = data.get("record_id")
    if record_id is None:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return
    await state.clear()
    try:
        async with open_service_context_by_id(
            panel_registry, message.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
            svc = ResellerService(session, ctx.xui)
            try:
                new_email = await svc.rename_service(
                    ctx.reseller, email, message.text or ""
                )
            except XuiError as e:
                await message.answer(str(e))
                return
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_message(message, e)
        return
    await message.answer(
        t.RENAME_OK.format(email=new_email), parse_mode="Markdown"
    )
    await _show_service_edit_menu(
        message, new_email, message.from_user.id, panel_registry, send_new=True
    )


@router.callback_query(F.data.startswith("edit_sub:"))
async def service_sub_regen_prompt(callback: CallbackQuery) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    email = await _service_email(callback.from_user.id, record_id)
    if email is None:
        await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.SUB_REGEN_CONFIRM.format(email=email),
        parse_mode="Markdown",
        reply_markup=sub_regen_confirm_kb(record_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_confirm:"))
async def service_sub_regen_confirm(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    try:
        async with open_service_context_by_id(
            panel_registry, callback.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
            svc = ResellerService(session, ctx.xui)
            try:
                await svc.regenerate_sub_id(ctx.reseller, email)
                delivery = await svc.get_delivery(ctx.reseller, email)
            except XuiError as e:
                await callback.answer(str(e), show_alert=True)
                return
            service_xui = ctx.xui
    except (ServiceNotFoundError, ServicePanelUnavailableError) as e:
        await answer_resolve_callback(callback, e)
        return
    await callback.message.edit_text(t.SUB_REGEN_OK)  # type: ignore[union-attr]
    await _send_delivery_with_qr(
        callback.message,  # type: ignore[arg-type]
        email,
        delivery,
        created=False,
        sub_public_url_configured=bool(service_xui.sub_public_url),
    )
    await _show_service_edit_menu(
        callback.message,  # type: ignore[arg-type]
        record_id,
        callback.from_user.id,
        panel_registry,
        send_new=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_limit:"))
async def service_edit_limit_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(record_id=record_id)
    await state.set_state(EditServiceStates.limit_ip)
    await callback.message.edit_text(t.LIMIT_IP_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("edit_comment:"))
async def service_edit_comment_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    record_id = _record_id_from(callback)
    if record_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(record_id=record_id)
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
    record_id = data.get("record_id")
    if record_id is None:
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
        async with open_service_context_by_id(
            panel_registry, message.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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
    record_id = data.get("record_id")
    if record_id is None:
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
        async with open_service_context_by_id(
            panel_registry, message.from_user.id, record_id
        ) as (ctx, session):
            email = ctx.record.email
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


@router.callback_query(
    F.data.in_({"traf_custom", "traf_confirm", "trafd_custom", "trafd_confirm"})
    | F.data.startswith("traf_vol:")
    | F.data.startswith("trafd_vol:")
)
async def stale_traffic_button(callback: CallbackQuery) -> None:
    """Buttons from an old traffic dialog whose FSM state is gone or changed."""
    await callback.answer(t.ACTION_EXPIRED, show_alert=True)
