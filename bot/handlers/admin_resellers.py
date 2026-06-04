"""Admin hub, detail view, and add-reseller wizard."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    reseller_admin_hub_kb,
    reseller_delete_confirm_kb,
    reseller_edit_add_quota_kb,
    reseller_edit_attach_inbounds_kb,
    reseller_edit_inbounds_kb,
    reseller_edit_max_clients_kb,
    reseller_edit_menu_kb,
    reseller_edit_quota_kb,
    reseller_reset_quota_confirm_kb,
    reseller_view_kb,
    reseller_wizard_confirm_kb,
    reseller_wizard_inbounds_kb,
    reseller_wizard_name_kb,
    reseller_wizard_pick_panel_kb,
    reseller_wizard_quota_kb,
)
from bot.states import AddResellerStates, EditResellerStates
from bot.texts import fa as t
from db.repository import (
    PanelRepository,
    ResellerRepository,
    inbound_ids_from_json,
    resolve_attach_inbound_ids,
)
from db.session import get_session_factory
from services.panel_registry import PanelNotFoundError, PanelRegistry
from services.quota import QuotaService, format_max_clients_admin
from services.reseller_edit import (
    ResellerNotFoundError,
    apply_add_quota,
    apply_allowed_inbounds,
    apply_attach_inbounds,
    apply_display_name,
    apply_max_clients,
    apply_quota,
    apply_reset_quota_usage,
    clear_max_clients_limit,
)
from services.reseller_labels import (
    InvalidDisplayNameError,
    normalize_display_name,
    reseller_label,
)
from xui.client import gb_to_bytes

router = Router()


async def _panel_names_for_resellers(
    session, resellers: list
) -> dict[int, str]:
    panel_repo = PanelRepository(session)
    names: dict[int, str] = {}
    for r in resellers:
        if r.panel_id not in names:
            p = await panel_repo.get(r.panel_id)
            names[r.panel_id] = p.name if p else f"#{r.panel_id}"
    return names


async def _reseller_hub_content() -> tuple[str, object]:
    async with get_session_factory()() as session:
        rows = await ResellerRepository(session).list_all()
        panel_names = await _panel_names_for_resellers(session, rows)

    if not rows:
        return f"{t.RESELLER_LIST_EMPTY}\n\n{t.RESELLER_HUB_HINT}", reseller_admin_hub_kb(
            [], {}
        )

    lines = [t.RESELLER_LIST_HEADER]
    for r in rows[:20]:
        name = r.display_name or str(r.telegram_id)
        p_name = panel_names.get(r.panel_id, f"#{r.panel_id}")
        status = "فعال" if r.is_active else "غیرفعال"
        lines.append(f"• {name} — {p_name} — {status}")
    if len(rows) > 20:
        lines.append(f"… و {len(rows) - 20} ریسلر دیگر")
    lines.append("")
    lines.append(t.RESELLER_HUB_HINT)
    return "\n".join(lines), reseller_admin_hub_kb(rows, panel_names)


async def _reseller_view_content(
    telegram_id: int,
) -> tuple[str, object] | None:
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(telegram_id)
        if not reseller:
            return None
        panel_repo = PanelRepository(session)
        panel = await panel_repo.get(reseller.panel_id)
        panel_name = panel.name if panel else f"#{reseller.panel_id}"
        st = await QuotaService(repo).status(reseller)
        client_count = st.client_count
        allowed = inbound_ids_from_json(reseller.allowed_inbound_ids)
        attach = resolve_attach_inbound_ids(reseller)

    text = t.RESELLER_VIEW_DETAIL.format(
        label=reseller_label(reseller),
        status="فعال" if reseller.is_active else "غیرفعال",
        panel_name=panel_name,
        panel_id=reseller.panel_id,
        quota_gb=st.quota_gb,
        active_gb=st.active_gb,
        lifetime_gb=st.lifetime_gb,
        remaining_gb=st.remaining_gb,
        client_count=client_count,
        max_clients_line=format_max_clients_admin(st),
        allowed_inbounds=", ".join(str(i) for i in allowed),
        attach_inbounds=", ".join(str(i) for i in attach),
    )
    markup = reseller_view_kb(
        telegram_id,
        is_active=reseller.is_active,
        can_change_panel=client_count == 0,
    )
    return text, markup


async def _send_reseller_hub(target: Message) -> None:
    text, markup = await _reseller_hub_content()
    await target.answer(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_reseller_hub(target: Message) -> None:
    text, markup = await _reseller_hub_content()
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_reseller_view(target: Message, telegram_id: int) -> bool:
    content = await _reseller_view_content(telegram_id)
    if content is None:
        return False
    text, markup = content
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]
    return True


async def _start_add_wizard(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddResellerStates.telegram_id)
    await message.answer(t.RESELLER_WIZARD_TELEGRAM_ID)


async def _go_to_name_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddResellerStates.display_name)
    await message.answer(
        t.RESELLER_WIZARD_DISPLAY_NAME,
        reply_markup=reseller_wizard_name_kb(),
    )


async def _go_to_panel_step(message: Message, state: FSMContext) -> None:
    async with get_session_factory()() as session:
        panels = await PanelRepository(session).list_active()
    if not panels:
        await message.answer(t.PANEL_SET_NO_PANELS)
        await state.clear()
        return
    await state.set_state(AddResellerStates.pick_panel)
    await message.answer(
        t.RESELLER_WIZARD_PICK_PANEL,
        reply_markup=reseller_wizard_pick_panel_kb(panels),
    )


async def _go_to_quota_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddResellerStates.quota)
    await message.answer(
        t.RESELLER_WIZARD_QUOTA,
        reply_markup=reseller_wizard_quota_kb(),
    )


async def _go_to_inbounds_step(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    data = await state.get_data()
    panel_id = data.get("panel_id")
    if panel_id is None:
        await message.answer(t.INVALID_INPUT)
        await state.clear()
        return
    try:
        xui = panel_registry.get_client(int(panel_id))
        inbounds = await xui.list_inbounds()
    except (PanelNotFoundError, Exception) as e:
        await message.answer(f"خطا در دریافت اینباندها: {e}")
        await state.clear()
        return
    if not inbounds:
        await message.answer(t.RESELLER_WIZARD_INBOUNDS_EMPTY)
        await state.clear()
        return
    await state.update_data(selected_inbounds=[], wizard_inbound_count=len(inbounds))
    await state.set_state(AddResellerStates.pick_inbounds)
    await message.answer(
        t.RESELLER_WIZARD_INBOUNDS.format(panel_id=panel_id),
        reply_markup=reseller_wizard_inbounds_kb(inbounds, set()),
    )


async def _refresh_inbounds_kb(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    data = await state.get_data()
    panel_id = data.get("panel_id")
    selected = set(data.get("selected_inbounds") or [])
    if panel_id is None:
        return
    xui = panel_registry.get_client(int(panel_id))
    inbounds = await xui.list_inbounds()
    await message.edit_reply_markup(
        reply_markup=reseller_wizard_inbounds_kb(inbounds, selected)
    )


async def _go_to_confirm_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(data["panel_id"])
    panel_name = panel.name if panel else f"#{data['panel_id']}"
    display = data.get("display_name") or "—"
    inbound_ids = data.get("selected_inbounds") or []
    await state.set_state(AddResellerStates.confirm)
    await message.answer(
        t.RESELLER_WIZARD_CONFIRM.format(
            telegram_id=data["telegram_id"],
            display_name=display,
            panel_name=panel_name,
            panel_id=data["panel_id"],
            quota_gb=data["quota_gb"],
            inbound_ids=", ".join(str(i) for i in sorted(inbound_ids)),
        ),
        reply_markup=reseller_wizard_confirm_kb(),
    )


@router.message(F.text == btn.LIST_RESELLERS)
@router.message(Command("list_resellers"))
async def reseller_hub(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await _send_reseller_hub(message)


@router.callback_query(F.data == "rsl:hub")
async def reseller_hub_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await _edit_reseller_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "rsl:add")
async def reseller_add_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _start_add_wizard(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:view:"))
async def reseller_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    await state.clear()
    content = await _reseller_view_content(tg_id)
    if content is None:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    text, markup = content
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:toggle:"))
async def reseller_toggle(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        row = await repo.get(tg_id)
        if not row:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        new_active = not row.is_active
        row = await repo.set_active(tg_id, new_active)
    assert row is not None
    msg = (
        t.RESELLER_ENABLED if new_active else t.RESELLER_DISABLED
    ).format(label=reseller_label(row))
    await callback.answer(msg, show_alert=True)
    await _edit_reseller_view(callback.message, tg_id)  # type: ignore[arg-type]


@router.callback_query(F.data.startswith("rsl:del:"))
async def reseller_delete_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or parts[2] == "yes":
        await callback.answer()
        return
    tg_id = int(parts[2])
    async with get_session_factory()() as session:
        row = await ResellerRepository(session).get(tg_id)
    if not row:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        t.RESELLER_DELETE_CONFIRM.format(label=reseller_label(row)),
        reply_markup=reseller_delete_confirm_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:del_yes:"))
async def reseller_delete_confirm(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        row = await repo.get(tg_id)
        if not row:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        label = reseller_label(row)
        try:
            await repo.delete(tg_id)
        except ValueError as e:
            client_count = await repo.client_count(tg_id)
            await callback.message.edit_text(
                t.RESELLER_DELETE_BLOCKED_HAS_CLIENTS.format(
                    label=label,
                    client_count=client_count,
                ),
                reply_markup=reseller_view_kb(
                    tg_id, is_active=row.is_active, can_change_panel=False
                ),
            )
            await callback.answer(str(e)[:200], show_alert=True)
            return
    await callback.answer(t.RESELLER_DELETED.format(label=label), show_alert=True)
    await _edit_reseller_hub(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "rsl:wiz_cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.RESELLER_WIZARD_CANCELLED)
    await callback.answer()


@router.message(AddResellerStates.telegram_id)
async def wizard_telegram_id(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        tg_id = int((message.text or "").strip())
        if tg_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    async with get_session_factory()() as session:
        existing = await ResellerRepository(session).get(tg_id)
    if existing:
        await message.answer(t.RESELLER_ALREADY_EXISTS)
        await state.clear()
        return
    await state.update_data(telegram_id=tg_id)
    await _go_to_name_step(message, state)


@router.callback_query(AddResellerStates.display_name, F.data == "rsl:name_skip")
async def wizard_name_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.update_data(display_name=None)
    if callback.message:
        await _go_to_panel_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddResellerStates.display_name)
async def wizard_display_name(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        display_name = normalize_display_name(message.text or "")
    except InvalidDisplayNameError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(display_name=display_name)
    await _go_to_panel_step(message, state)


@router.callback_query(AddResellerStates.pick_panel, F.data.startswith("rsl:pan:"))
async def wizard_pick_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
    if not panel:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    await state.update_data(panel_id=panel_id, panel_name=panel.name)
    await _go_to_quota_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(AddResellerStates.quota, F.data.startswith("rsl:quota:"))
async def wizard_quota_quick(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        quota = float(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if quota <= 0:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(quota_gb=quota)
    await _go_to_inbounds_step(callback.message, state, panel_registry)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddResellerStates.quota)
async def wizard_quota_text(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        quota = float((message.text or "").replace(",", "."))
        if quota <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(quota_gb=quota)
    await _go_to_inbounds_step(message, state, panel_registry)


@router.callback_query(AddResellerStates.pick_inbounds, F.data.startswith("rsl:ib:t:"))
async def wizard_inbound_toggle(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    ib_id = int(callback.data.split(":", 3)[3])
    data = await state.get_data()
    selected: list[int] = list(data.get("selected_inbounds") or [])
    if ib_id in selected:
        selected.remove(ib_id)
    else:
        selected.append(ib_id)
    await state.update_data(selected_inbounds=selected)
    await _refresh_inbounds_kb(callback.message, state, panel_registry)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(AddResellerStates.pick_inbounds, F.data == "rsl:ib:done")
async def wizard_inbounds_done(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    selected = data.get("selected_inbounds") or []
    if not selected:
        await callback.answer(
            t.RESELLER_WIZARD_INBOUNDS_NONE_SELECTED, show_alert=True
        )
        return
    if callback.message:
        await _go_to_confirm_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(AddResellerStates.confirm, F.data == "rsl:wiz_save")
async def wizard_save(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    required = ("telegram_id", "panel_id", "quota_gb", "selected_inbounds")
    if not all(k in data for k in required):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    inbound_ids = sorted(int(x) for x in data["selected_inbounds"])
    tg_id = int(data["telegram_id"])
    panel_id = int(data["panel_id"])
    quota_gb = float(data["quota_gb"])
    display_name = data.get("display_name")

    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
        if not panel:
            await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
            return
        if not panel.is_active:
            await callback.answer(
                t.PANEL_INACTIVE_FOR_RESELLER.format(
                    panel_name=panel.name, panel_id=panel_id
                ),
                show_alert=True,
            )
            return
        row = await ResellerRepository(session).upsert(
            tg_id,
            gb_to_bytes(quota_gb),
            inbound_ids,
            panel_id=panel_id,
            attach_inbound_ids=inbound_ids,
            display_name=display_name,
        )
        await panel_registry.reload_panel(session, panel_id)

    await state.clear()
    ids_s = ", ".join(str(i) for i in inbound_ids)
    text = t.RESELLER_ADDED.format(
        label=reseller_label(row),
        panel_id=panel_id,
        panel_name=panel.name,
        quota_gb=quota_gb,
        allowed_inbounds=ids_s,
        attach_inbounds=ids_s,
    )
    if callback.message:
        await callback.message.edit_text(text)
    await callback.answer()


async def _finish_edit_view(
    message: Message, state: FSMContext, telegram_id: int, notice: str
) -> None:
    await state.clear()
    content = await _reseller_view_content(telegram_id)
    if content is None:
        await message.edit_text(notice)
        return
    text, markup = content
    await message.edit_text(f"{notice}\n\n{text}", reply_markup=markup)


async def _reseller_for_edit(telegram_id: int):
    async with get_session_factory()() as session:
        return await ResellerRepository(session).get(telegram_id)


@router.callback_query(F.data.startswith("rsl:edit:"))
async def reseller_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    await state.clear()
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        t.RESELLER_EDIT_MENU.format(label=reseller_label(reseller)),
        reply_markup=reseller_edit_menu_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:edit_cancel:"))
async def reseller_edit_cancel(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    await state.clear()
    if not await _edit_reseller_view(callback.message, tg_id):  # type: ignore[arg-type]
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:quota:"))
async def edit_start_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await state.set_state(EditResellerStates.value)
    await state.update_data(reseller_tg_id=tg_id, edit_kind="quota")
    await callback.message.edit_text(
        t.RESELLER_EDIT_QUOTA_PROMPT.format(label=reseller_label(reseller)),
        reply_markup=reseller_edit_quota_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:eq:"))
async def edit_quota_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    quota_gb = float(parts[2])
    tg_id = int(parts[3])
    async with get_session_factory()() as session:
        try:
            result = await apply_quota(session, tg_id, quota_gb)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
    await _finish_edit_view(callback.message, state, tg_id, result.message_text)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:addq:"))
async def edit_start_add_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await state.set_state(EditResellerStates.value)
    await state.update_data(reseller_tg_id=tg_id, edit_kind="add_quota")
    await callback.message.edit_text(
        t.RESELLER_EDIT_ADD_QUOTA_PROMPT.format(label=reseller_label(reseller)),
        reply_markup=reseller_edit_add_quota_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:eaq:"))
async def edit_add_quota_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    add_gb = float(parts[2])
    tg_id = int(parts[3])
    async with get_session_factory()() as session:
        try:
            result = await apply_add_quota(session, tg_id, add_gb)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        except ValueError as e:
            await callback.answer(str(e)[:200], show_alert=True)
            return
    await _finish_edit_view(callback.message, state, tg_id, result.message_text)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:resetu:"))
async def edit_start_reset_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        t.RESELLER_RESET_QUOTA_CONFIRM.format(label=reseller_label(reseller)),
        reply_markup=reseller_reset_quota_confirm_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:resetu:yes:"))
async def edit_reset_quota_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    async with get_session_factory()() as session:
        try:
            result = await apply_reset_quota_usage(session, tg_id)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
    await _finish_edit_view(callback.message, state, tg_id, result.message_text)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:resetu:no:"))
async def edit_reset_quota_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    if not await _edit_reseller_view(callback.message, tg_id):  # type: ignore[arg-type]
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:name:"))
async def edit_start_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await state.set_state(EditResellerStates.value)
    await state.update_data(reseller_tg_id=tg_id, edit_kind="name")
    await callback.message.edit_text(
        t.RESELLER_EDIT_NAME_PROMPT.format(label=reseller_label(reseller))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:maxc:"))
async def edit_start_max_clients(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    await state.set_state(EditResellerStates.value)
    await state.update_data(reseller_tg_id=tg_id, edit_kind="max_clients")
    await callback.message.edit_text(
        t.RESELLER_EDIT_MAX_CLIENTS_PROMPT.format(label=reseller_label(reseller)),
        reply_markup=reseller_edit_max_clients_kb(tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:emc:set:"))
async def edit_max_clients_quick(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    max_clients = int(parts[3])
    tg_id = int(parts[4])
    async with get_session_factory()() as session:
        try:
            result = await apply_max_clients(session, tg_id, max_clients)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
    await _finish_edit_view(callback.message, state, tg_id, result.message_text)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:emc:clear:"))
async def edit_max_clients_clear(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    async with get_session_factory()() as session:
        try:
            result = await clear_max_clients_limit(session, tg_id)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
    await _finish_edit_view(callback.message, state, tg_id, result.message_text)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:allow:"))
async def edit_start_allowed(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    try:
        xui = panel_registry.get_client(reseller.panel_id)
        inbounds = await xui.list_inbounds()
    except (PanelNotFoundError, Exception) as e:
        await callback.answer(str(e)[:200], show_alert=True)
        return
    if not inbounds:
        await callback.answer(t.RESELLER_WIZARD_INBOUNDS_EMPTY, show_alert=True)
        return
    selected = set(inbound_ids_from_json(reseller.allowed_inbound_ids))
    await state.set_state(EditResellerStates.pick_inbounds)
    await state.update_data(
        reseller_tg_id=tg_id,
        edit_kind="allowed",
        selected_inbounds=sorted(selected),
        panel_id=reseller.panel_id,
    )
    await callback.message.edit_text(
        t.RESELLER_EDIT_ALLOW_PROMPT.format(
            panel_id=reseller.panel_id,
        ),
        reply_markup=reseller_edit_inbounds_kb(inbounds, selected, tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:ev:attach:"))
async def edit_start_attach(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 3)[3])
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    allowed = inbound_ids_from_json(reseller.allowed_inbound_ids)
    if not allowed:
        await callback.answer(t.RESELLER_EDIT_ATTACH_EMPTY_ALLOWED, show_alert=True)
        return
    selected = set(resolve_attach_inbound_ids(reseller))
    await state.set_state(EditResellerStates.pick_inbounds)
    await state.update_data(
        reseller_tg_id=tg_id,
        edit_kind="attach",
        selected_inbounds=sorted(selected),
    )
    await callback.message.edit_text(
        t.RESELLER_EDIT_ATTACH_PROMPT,
        reply_markup=reseller_edit_attach_inbounds_kb(allowed, selected, tg_id),
    )
    await callback.answer()


@router.callback_query(
    EditResellerStates.pick_inbounds, F.data.startswith("rsl:eib:t:")
)
async def edit_inbound_toggle(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    ib_id = int(callback.data.split(":", 3)[3])
    data = await state.get_data()
    tg_id = int(data["reseller_tg_id"])
    selected: list[int] = list(data.get("selected_inbounds") or [])
    if ib_id in selected:
        selected.remove(ib_id)
    else:
        selected.append(ib_id)
    await state.update_data(selected_inbounds=selected)
    edit_kind = data.get("edit_kind")
    if edit_kind == "attach":
        async with get_session_factory()() as session:
            reseller = await ResellerRepository(session).get(tg_id)
        assert reseller is not None
        allowed = inbound_ids_from_json(reseller.allowed_inbound_ids)
        await callback.message.edit_reply_markup(
            reply_markup=reseller_edit_attach_inbounds_kb(
                allowed, set(selected), tg_id
            ),
        )
    else:
        panel_id = data.get("panel_id")
        xui = panel_registry.get_client(int(panel_id))
        inbounds = await xui.list_inbounds()
        await callback.message.edit_reply_markup(
            reply_markup=reseller_edit_inbounds_kb(
                inbounds, set(selected), tg_id
            ),
        )
    await callback.answer()


@router.callback_query(EditResellerStates.pick_inbounds, F.data == "rsl:eib:done")
async def edit_inbounds_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    tg_id = int(data["reseller_tg_id"])
    selected = data.get("selected_inbounds") or []
    if not selected:
        await callback.answer(t.RESELLER_EDIT_INBOUNDS_NONE, show_alert=True)
        return
    inbound_ids = sorted(int(x) for x in selected)
    edit_kind = data.get("edit_kind")
    async with get_session_factory()() as session:
        try:
            if edit_kind == "allowed":
                result = await apply_allowed_inbounds(session, tg_id, inbound_ids)
            else:
                result = await apply_attach_inbounds(session, tg_id, inbound_ids)
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        except ValueError as e:
            await callback.answer(str(e)[:200], show_alert=True)
            return
    if callback.message:
        await _finish_edit_view(
            callback.message, state, tg_id, result.message_text
        )
    await callback.answer()


@router.message(EditResellerStates.value)
async def edit_value_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    tg_id = int(data["reseller_tg_id"])
    kind = data.get("edit_kind")
    text_in = (message.text or "").strip()

    async with get_session_factory()() as session:
        try:
            if kind == "quota":
                quota_gb = float(text_in.replace(",", "."))
                if quota_gb <= 0:
                    raise ValueError
                result = await apply_quota(session, tg_id, quota_gb)
            elif kind == "add_quota":
                add_gb = float(text_in.replace(",", "."))
                if add_gb <= 0:
                    raise ValueError
                result = await apply_add_quota(session, tg_id, add_gb)
            elif kind == "name":
                display_name = normalize_display_name(text_in)
                result = await apply_display_name(session, tg_id, display_name)
            elif kind == "max_clients":
                max_clients = int(text_in)
                if max_clients < 1:
                    raise ValueError
                result = await apply_max_clients(session, tg_id, max_clients)
            else:
                await message.answer(t.INVALID_INPUT)
                return
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            await state.clear()
            return
        except (ValueError, InvalidDisplayNameError):
            await message.answer(t.INVALID_INPUT)
            return

    await state.clear()
    content = await _reseller_view_content(tg_id)
    if content is None:
        await message.answer(result.message_text)
        return
    view_text, markup = content
    await message.answer(
        f"{result.message_text}\n\n{view_text}",
        reply_markup=markup,
    )
