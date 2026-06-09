"""Admin: per-panel assignment management for resellers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.handlers.admin_resellers import (
    _finish_edit_view,
    _reseller_for_edit,
)
from bot.keyboards.common import (
    reseller_panel_add_pick_kb,
    reseller_panel_assignment_kb,
    reseller_panel_edit_menu_kb,
    reseller_panel_list_kb,
    reseller_panel_remove_confirm_kb,
    reseller_wizard_inbounds_kb,
    reseller_wizard_quota_kb,
)
from bot.states import AddResellerPanelStates, EditResellerStates
from bot.texts import fa as t
from db.repository import PanelRepository, ResellerPanelRepository, ResellerRepository
from db.session import get_session_factory
from services.panel_registry import PanelNotFoundError, PanelRegistry
from services.quota import QuotaService
from services.reseller_labels import reseller_label
from services.reseller_panel_edit import (
    AssignmentNotFoundError,
    PanelNotFoundError,
    ResellerNotFoundError,
    apply_add_panel_assignment,
    apply_panel_add_quota,
    apply_panel_allowed_inbounds,
    apply_panel_attach_inbounds,
    apply_panel_max_clients,
    apply_panel_quota,
    apply_panel_reset_quota_usage,
    apply_panel_toggle_create_allowed,
    apply_remove_panel_assignment,
    apply_set_default_panel,
)

router = Router()


def _parse_tg_panel(data: str, prefix: str) -> tuple[int, int]:
    rest = data[len(prefix) :]
    parts = rest.split(":")
    if len(parts) < 2:
        raise ValueError
    return int(parts[0]), int(parts[1])


async def _panel_assignment_content(
    telegram_id: int, panel_id: int
) -> tuple[str, object] | None:
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(telegram_id)
        if not reseller:
            return None
        assignment = await ResellerPanelRepository(session).get(
            telegram_id, panel_id
        )
        if not assignment:
            return None
        panel = await PanelRepository(session).get(panel_id)
        panel_name = panel.name if panel else f"#{panel_id}"
        st = await QuotaService(
            ResellerRepository(session), ResellerPanelRepository(session)
        ).status(reseller, panel_id)
        from db.repository import (
            format_inbound_summary_for_assignment,
            inbound_ids_from_json,
            resolve_attach_inbound_ids_for_assignment,
        )

        allowed = inbound_ids_from_json(assignment.allowed_inbound_ids)
        attach = resolve_attach_inbound_ids_for_assignment(assignment)
        default_mark = " (پیش‌فرض)" if reseller.panel_id == panel_id else ""
        text = t.RESELLER_PANEL_VIEW.format(
            label=reseller_label(reseller),
            panel_name=panel_name + default_mark,
            panel_id=panel_id,
            status="ساخت: مجاز" if assignment.is_active else "ساخت: ممنوع",
            quota_gb=st.quota_gb,
            active_gb=st.active_gb,
            lifetime_gb=st.lifetime_gb,
            remaining_gb=st.remaining_gb,
            client_count=st.client_count,
            max_clients=st.max_clients if st.max_clients is not None else "نامحدود",
            allowed_inbounds=", ".join(str(i) for i in allowed),
            attach_inbounds=", ".join(str(i) for i in attach),
        )
        markup = reseller_panel_assignment_kb(
            telegram_id,
            panel_id,
            is_default=reseller.panel_id == panel_id,
            can_remove=st.client_count == 0,
            assignment_is_active=assignment.is_active,
        )
    return text, markup


@router.callback_query(F.data.startswith("rsl:panels:"))
async def reseller_panels_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    await state.clear()
    async with get_session_factory()() as session:
        reseller = await ResellerRepository(session).get(tg_id)
        if not reseller:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        assignments = await ResellerPanelRepository(session).list_for_reseller(tg_id)
        panel_repo = PanelRepository(session)
        lines = [t.RESELLER_PANELS_HEADER.format(label=reseller_label(reseller))]
        panel_labels: dict[int, str] = {}
        for a in assignments:
            p = await panel_repo.get(a.panel_id)
            name = p.name if p else f"#{a.panel_id}"
            panel_labels[a.panel_id] = name
            st = await QuotaService(
                ResellerRepository(session), ResellerPanelRepository(session)
            ).status(reseller, a.panel_id)
            default = " *" if reseller.panel_id == a.panel_id else ""
            blocked = " ⏸" if not a.is_active else ""
            lines.append(
                f"• {name}{default}{blocked}: {st.remaining_gb:.1f}/{st.quota_gb:.1f} GB — "
                f"{st.client_count} سرویس"
            )
    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=reseller_panel_list_kb(tg_id, assignments, panel_labels),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:pview:\d+:\d+$"))
async def reseller_panel_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pview:")
    await state.clear()
    content = await _panel_assignment_content(tg_id, panel_id)
    if not content:
        await callback.answer("تخصیص یافت نشد.", show_alert=True)
        return
    text, markup = content
    await callback.message.edit_text(text, reply_markup=markup)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:pedit:\d+:\d+$"))
async def reseller_panel_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pedit:")
    await state.clear()
    reseller = await _reseller_for_edit(tg_id)
    if not reseller:
        await callback.answer("ریسلر یافت نشد.", show_alert=True)
        return
    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
    panel_name = panel.name if panel else f"#{panel_id}"
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RESELLER_PANEL_EDIT_MENU.format(
            label=reseller_label(reseller), panel_name=panel_name
        ),
        reply_markup=reseller_panel_edit_menu_kb(tg_id, panel_id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:ptoggle:\d+:\d+$"))
async def reseller_panel_toggle_create(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:ptoggle:")
    async with get_session_factory()() as session:
        try:
            result = await apply_panel_toggle_create_allowed(
                session, tg_id, panel_id
            )
        except (ResellerNotFoundError, AssignmentNotFoundError):
            await callback.answer("یافت نشد.", show_alert=True)
            return
    content = await _panel_assignment_content(tg_id, panel_id)
    if content:
        text, markup = content
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"{result.message_text}\n\n{text}", reply_markup=markup
        )
    await callback.answer(result.message_text)


@router.callback_query(F.data.regexp(r"^rsl:pdefault:\d+:\d+$"))
async def reseller_panel_set_default(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pdefault:")
    async with get_session_factory()() as session:
        try:
            result = await apply_set_default_panel(session, tg_id, panel_id)
        except (ResellerNotFoundError, AssignmentNotFoundError):
            await callback.answer("یافت نشد.", show_alert=True)
            return
    content = await _panel_assignment_content(tg_id, panel_id)
    if content:
        text, markup = content
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"{result.message_text}\n\n{text}", reply_markup=markup
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:premove:\d+:\d+$"))
async def reseller_panel_remove_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:premove:")
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.PANEL_REMOVE_CONFIRM,
        reply_markup=reseller_panel_remove_confirm_kb(tg_id, panel_id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:premove_yes:\d+:\d+$"))
async def reseller_panel_remove_confirm(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:premove_yes:")
    async with get_session_factory()() as session:
        try:
            result = await apply_remove_panel_assignment(session, tg_id, panel_id)
        except (ResellerNotFoundError, AssignmentNotFoundError, ValueError) as e:
            await callback.answer(str(e)[:200], show_alert=True)
            return
    await callback.message.edit_text(result.message_text)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:padd:"))
async def reseller_panel_add_start(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        assigned = {
            a.panel_id
            for a in await ResellerPanelRepository(session).list_for_reseller(tg_id)
        }
        panels = [
            p for p in await PanelRepository(session).list_active() if p.id not in assigned
        ]
    if not panels:
        await callback.answer(t.NO_PANEL_AVAILABLE, show_alert=True)
        return
    await state.set_state(AddResellerPanelStates.pick_panel)
    await state.update_data(reseller_tg_id=tg_id, selected_inbounds=[])
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RESELLER_PANEL_ADD_PICK,
        reply_markup=reseller_panel_add_pick_kb(panels, tg_id),
    )
    await callback.answer()


@router.callback_query(
    AddResellerPanelStates.pick_panel, F.data.regexp(r"^rsl:padd_pan:\d+:\d+$")
)
async def reseller_panel_add_pick_panel(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    panel_id = int(parts[2])
    tg_id = int(parts[3])
    await state.update_data(reseller_tg_id=tg_id, panel_id=panel_id)
    await state.set_state(AddResellerPanelStates.quota)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RESELLER_PANEL_ADD_QUOTA,
        reply_markup=reseller_wizard_quota_kb(),
    )
    await callback.answer()


@router.callback_query(AddResellerPanelStates.quota, F.data.startswith("rsl:quota:"))
async def reseller_panel_add_quota(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    quota_gb = float(callback.data.split(":", 2)[2])
    data = await state.get_data()
    panel_id = data.get("panel_id")
    if panel_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(quota_gb=quota_gb)
    try:
        xui = panel_registry.get_client(int(panel_id))
    except PanelNotFoundError:
        await callback.answer(t.PANEL_NOT_LOADED, show_alert=True)
        return
    inbounds = await xui.list_inbounds()
    await state.set_state(AddResellerPanelStates.inbounds)
    await state.update_data(selected_inbounds=[])
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.RESELLER_WIZARD_INBOUNDS.format(panel_id=panel_id),
        reply_markup=reseller_wizard_inbounds_kb(
            inbounds,
            set(),
            toggle_prefix="rsl:pib:t:",
            done_callback="rsl:pib:done",
        ),
    )
    await callback.answer()


@router.callback_query(
    AddResellerPanelStates.inbounds, F.data.startswith("rsl:pib:t:")
)
async def reseller_panel_add_inbound_toggle(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    ib_id = int(callback.data.split(":", 3)[3])
    data = await state.get_data()
    selected = set(data.get("selected_inbounds", []))
    if ib_id in selected:
        selected.discard(ib_id)
    else:
        selected.add(ib_id)
    await state.update_data(selected_inbounds=list(selected))
    panel_id = int(data["panel_id"])
    xui = panel_registry.get_client(panel_id)
    inbounds = await xui.list_inbounds()
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=reseller_wizard_inbounds_kb(
            inbounds,
            selected,
            toggle_prefix="rsl:pib:t:",
            done_callback="rsl:pib:done",
        )
    )
    await callback.answer()


@router.callback_query(AddResellerPanelStates.inbounds, F.data == "rsl:pib:done")
async def reseller_panel_add_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    tg_id = data.get("reseller_tg_id")
    panel_id = data.get("panel_id")
    quota_gb = data.get("quota_gb")
    selected = data.get("selected_inbounds", [])
    if not tg_id or panel_id is None or quota_gb is None or not selected:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    async with get_session_factory()() as session:
        try:
            result = await apply_add_panel_assignment(
                session,
                int(tg_id),
                int(panel_id),
                float(quota_gb),
                [int(x) for x in selected],
            )
        except (ResellerNotFoundError, PanelNotFoundError, ValueError) as e:
            await callback.answer(str(e)[:200], show_alert=True)
            return
    await state.clear()
    await callback.message.edit_text(result.message_text)  # type: ignore[union-attr]
    await callback.answer()


# Panel-scoped edit handlers (quota, inbounds, ...)
@router.callback_query(F.data.regexp(r"^rsl:pev:quota:\d+:\d+$"))
async def panel_edit_start_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pev:quota:")
    await state.set_state(EditResellerStates.value)
    await state.update_data(
        reseller_tg_id=tg_id, panel_id=panel_id, edit_kind="quota"
    )
    await callback.message.edit_text(t.RESELLER_EDIT_QUOTA_PROMPT.format(label=str(tg_id)))
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:peq:\d+(\.\d+)?:\d+:\d+$"))
async def panel_edit_quota_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    quota_gb = float(parts[2])
    tg_id, panel_id = int(parts[3]), int(parts[4])
    async with get_session_factory()() as session:
        try:
            result = await apply_panel_quota(session, tg_id, panel_id, quota_gb)
        except (ResellerNotFoundError, AssignmentNotFoundError):
            await callback.answer("یافت نشد.", show_alert=True)
            return
    content = await _panel_assignment_content(tg_id, panel_id)
    if content:
        text, markup = content
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"{result.message_text}\n\n{text}", reply_markup=markup
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:pev:addq:\d+:\d+$"))
async def panel_edit_start_add_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pev:addq:")
    await state.set_state(EditResellerStates.value)
    await state.update_data(
        reseller_tg_id=tg_id, panel_id=panel_id, edit_kind="add_quota"
    )
    await callback.message.edit_text(t.RESELLER_EDIT_ADD_QUOTA_PROMPT.format(label=str(tg_id)))
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:peaq:\d+(\.\d+)?:\d+:\d+$"))
async def panel_edit_add_quota_quick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    add_gb = float(parts[2])
    tg_id, panel_id = int(parts[3]), int(parts[4])
    async with get_session_factory()() as session:
        try:
            result = await apply_panel_add_quota(session, tg_id, panel_id, add_gb)
        except (ResellerNotFoundError, AssignmentNotFoundError, ValueError) as e:
            await callback.answer(str(e)[:200], show_alert=True)
            return
    content = await _panel_assignment_content(tg_id, panel_id)
    if content:
        text, markup = content
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"{result.message_text}\n\n{text}", reply_markup=markup
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsl:pev:resetu:\d+:\d+$"))
async def panel_edit_reset_quota(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id, panel_id = _parse_tg_panel(callback.data, "rsl:pev:resetu:")
    async with get_session_factory()() as session:
        try:
            result = await apply_panel_reset_quota_usage(session, tg_id, panel_id)
        except (ResellerNotFoundError, AssignmentNotFoundError):
            await callback.answer("یافت نشد.", show_alert=True)
            return
    content = await _panel_assignment_content(tg_id, panel_id)
    if content:
        text, markup = content
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"{result.message_text}\n\n{text}", reply_markup=markup
        )
    await callback.answer()
