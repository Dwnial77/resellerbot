"""Admin hub and wizard for multiple 3x-ui panels."""

import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.utils.panel_url import InvalidPanelUrlError, normalize_http_url, normalize_sub_public_url
from bot.keyboards.common import (
    panel_admin_hub_kb,
    panel_bulk_confirm_kb,
    panel_bulk_inbounds_kb,
    panel_delete_confirm_kb,
    panel_edit_menu_kb,
    panel_edit_sub_kb,
    panel_view_kb,
    panel_wizard_confirm_kb,
    panel_wizard_skip_sub_kb,
)
from bot.states import AddPanelStates, EditPanelStates
from bot.texts import fa as t
from db.repository import PanelRepository
from db.session import get_session_factory
from services.bulk_inbounds import (
    apply_bulk_inbound,
    count_resellers_with_inbound,
    diagnose_panel_inbounds,
    orphan_inbound_ids,
)
from services.panel_edit import (
    PanelConnectionError,
    apply_panel_api_token,
    apply_panel_base_url,
    apply_panel_name,
    apply_panel_sub_public_url,
)
from services.panel_registry import PanelNotFoundError, PanelRegistry
from xui.client import XuiClient, XuiError

logger = logging.getLogger(__name__)
router = Router()


async def _panel_hub_text() -> tuple[str, object]:
    async with get_session_factory()() as session:
        panels = await PanelRepository(session).list_all()
    if not panels:
        return t.PANEL_LIST_EMPTY + "\n\n" + t.PANEL_HUB_HINT, panel_admin_hub_kb([])
    lines = [t.PANEL_LIST_HEADER]
    for p in panels:
        status = "فعال" if p.is_active else "غیرفعال"
        lines.append(f"• #{p.id} — {p.name} — {p.base_url} ({status})")
    return "\n".join(lines), panel_admin_hub_kb(panels)


async def _send_panel_hub(target: Message) -> None:
    text, markup = await _panel_hub_text()
    await target.answer(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_panel_hub(target: Message) -> None:
    text, markup = await _panel_hub_text()
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]


def _panel_summary(p) -> str:
    sub = p.sub_public_url or "—"
    return (
        f"پنل #{p.id}: {p.name}\n"
        f"آدرس: {p.base_url}\n"
        f"ساب عمومی: {sub}\n"
        f"وضعیت: {'فعال' if p.is_active else 'غیرفعال'}"
    )


@router.message(F.text == btn.PANELS)
@router.message(Command("panels"))
async def panel_hub(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await _send_panel_hub(message)


@router.callback_query(F.data == "pnl:hub")
async def panel_hub_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _edit_panel_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "pnl:add")
async def panel_add_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    await state.set_state(AddPanelStates.name)
    if callback.message:
        await callback.message.answer(t.PANEL_WIZARD_NAME)  # type: ignore[union-attr]
    await callback.answer()


@router.message(AddPanelStates.name)
async def wizard_panel_name(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(name=name)
    await state.set_state(AddPanelStates.base_url)
    await message.answer(t.PANEL_WIZARD_URL)


@router.message(AddPanelStates.base_url)
async def wizard_panel_url(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        url = normalize_http_url(message.text or "")
    except InvalidPanelUrlError as e:
        await message.answer(str(e))
        return
    await state.update_data(base_url=url)
    await state.set_state(AddPanelStates.api_token)
    await message.answer(t.PANEL_WIZARD_TOKEN)


@router.message(AddPanelStates.api_token)
async def wizard_panel_token(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    token = (message.text or "").strip()
    if not token:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(api_token=token)
    await state.set_state(AddPanelStates.sub_url)
    await message.answer(
        t.PANEL_WIZARD_SUB,
        reply_markup=panel_wizard_skip_sub_kb(),
    )


@router.callback_query(AddPanelStates.sub_url, F.data == "pnl:wiz_skip_sub")
async def wizard_skip_sub(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.update_data(sub_public_url=None)
    if callback.message:
        await _wizard_confirm_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddPanelStates.sub_url)
async def wizard_panel_sub(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        sub = normalize_sub_public_url(message.text or "")
    except InvalidPanelUrlError as e:
        await message.answer(str(e))
        return
    await state.update_data(sub_public_url=sub)
    await _wizard_confirm_step(message, state)


async def _wizard_confirm_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AddPanelStates.confirm)
    sub = data.get("sub_public_url") or "—"
    await message.answer(
        t.PANEL_WIZARD_CONFIRM.format(
            name=data["name"],
            base_url=data["base_url"],
            sub_public_url=sub,
        ),
        reply_markup=panel_wizard_confirm_kb(),
    )


@router.callback_query(AddPanelStates.confirm, F.data == "pnl:wiz_cancel")
@router.callback_query(F.data == "pnl:wiz_cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.PANEL_WIZARD_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(AddPanelStates.confirm, F.data == "pnl:wiz_save")
async def wizard_save(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    required = ("name", "base_url", "api_token")
    if not all(k in data for k in required):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    test_client = XuiClient(
        data["base_url"],
        api_token=data["api_token"],
        sub_public_url=data.get("sub_public_url"),
    )
    try:
        await test_client.ensure_authenticated()
    except Exception as e:
        await callback.answer(
            t.PANEL_AUTH_FAILED.format(error=str(e)[:200]),
            show_alert=True,
        )
        await test_client.close()
        return
    await test_client.close()

    async with get_session_factory()() as session:
        repo = PanelRepository(session)
        try:
            row = await repo.create(
                data["name"],
                data["base_url"],
                api_token=data["api_token"],
                sub_public_url=data.get("sub_public_url"),
            )
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return
        await panel_registry.reload_panel(session, row.id)

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t.PANEL_ADDED.format(id=row.id, name=row.name, base_url=row.base_url)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:view:"))
async def panel_view(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message or not callback.data:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(panel_id)
    if not row:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(
        _panel_summary(row),
        reply_markup=panel_view_kb(panel_id, is_active=row.is_active),
    )
    await callback.answer()


async def _refresh_panel_view(
    message: Message, panel_id: int, *, prefix: str = ""
) -> None:
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(panel_id)
    if not row:
        await message.edit_text(t.PANEL_NOT_FOUND)
        return
    text = _panel_summary(row)
    if prefix:
        text = f"{prefix}\n\n{text}"
    await message.edit_text(
        text,
        reply_markup=panel_view_kb(panel_id, is_active=row.is_active),
    )


@router.callback_query(F.data.startswith("pnl:edit:"))
async def panel_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message or not callback.data:
        return
    await state.clear()
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(panel_id)
    if not row:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(
        t.PANEL_EDIT_MENU.format(id=panel_id, name=row.name),
        reply_markup=panel_edit_menu_kb(panel_id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^pnl:pev:(name|url|token|sub):\d+$"))
async def panel_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message or not callback.data:
        return
    parts = callback.data.split(":")
    kind = parts[2]
    panel_id = int(parts[3])
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(panel_id)
    if not row:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    await state.set_state(EditPanelStates.value)
    await state.update_data(panel_id=panel_id, edit_kind=kind)
    prompts = {
        "name": t.PANEL_EDIT_NAME_PROMPT,
        "url": t.PANEL_EDIT_URL_PROMPT,
        "token": t.PANEL_EDIT_TOKEN_PROMPT,
        "sub": t.PANEL_EDIT_SUB_PROMPT,
    }
    markup = panel_edit_sub_kb(panel_id) if kind == "sub" else None
    await callback.message.edit_text(
        prompts[kind].format(id=panel_id, name=row.name),
        reply_markup=markup,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:sub_clear:"))
async def panel_edit_sub_clear(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message or not callback.data:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    await state.clear()
    async with get_session_factory()() as session:
        try:
            result = await apply_panel_sub_public_url(session, panel_id, None)
        except PanelNotFoundError:
            await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
            return
        await panel_registry.reload_panel(session, panel_id)
    await _refresh_panel_view(
        callback.message, panel_id, prefix=result.message_text  # type: ignore[arg-type]
    )
    await callback.answer()


@router.message(EditPanelStates.value)
async def panel_edit_value(
    message: Message, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    panel_id = data.get("panel_id")
    kind = data.get("edit_kind")
    text_in = (message.text or "").strip()
    if panel_id is None or not kind:
        await state.clear()
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            if kind == "name":
                if not text_in:
                    raise ValueError
                result = await apply_panel_name(session, int(panel_id), text_in)
            elif kind == "url":
                result = await apply_panel_base_url(
                    session, int(panel_id), text_in
                )
            elif kind == "token":
                if not text_in:
                    raise ValueError
                result = await apply_panel_api_token(
                    session, int(panel_id), text_in
                )
            elif kind == "sub":
                try:
                    sub = normalize_sub_public_url(text_in)
                except InvalidPanelUrlError as e:
                    await message.answer(str(e))
                    return
                result = await apply_panel_sub_public_url(
                    session, int(panel_id), sub
                )
            else:
                await message.answer(t.INVALID_INPUT)
                return
        except PanelNotFoundError:
            await state.clear()
            await message.answer(t.PANEL_NOT_FOUND)
            return
        except PanelConnectionError as e:
            await message.answer(t.PANEL_AUTH_FAILED.format(error=e.message))
            return
        except (ValueError, InvalidPanelUrlError):
            await message.answer(t.INVALID_INPUT)
            return

        await panel_registry.reload_panel(session, int(panel_id))

    await state.clear()
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(int(panel_id))
    if not row:
        await message.answer(result.message_text)
        return
    summary = _panel_summary(row)
    await message.answer(
        f"{result.message_text}\n\n{summary}",
        reply_markup=panel_view_kb(int(panel_id), is_active=row.is_active),
    )


@router.callback_query(F.data.startswith("pnl:toggle:"))
async def panel_toggle(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        repo = PanelRepository(session)
        row = await repo.get(panel_id)
        if not row:
            await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
            return
        row = await repo.set_active(panel_id, not row.is_active)
        assert row is not None
        await panel_registry.reload_panel(session, panel_id)

    await callback.message.edit_text(
        _panel_summary(row),
        reply_markup=panel_view_kb(panel_id, is_active=row.is_active),
    )
    await callback.answer()


class _PanelUnreachable(Exception):
    """Panel could not be reached — distinct from 'the data looks wrong'."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    async def message(self, panel_id: int) -> str:
        async with get_session_factory()() as session:
            panel = await PanelRepository(session).get(panel_id)
        name = panel.name if panel else f"#{panel_id}"
        return t.PANEL_UNREACHABLE.format(panel_name=name, reason=self.reason)


def _network_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "اتصال برقرار نشد (DNS یا شبکه)."
    if isinstance(exc, httpx.TimeoutException):
        return "پاسخی از پنل دریافت نشد (timeout)."
    return str(exc)[:150]


async def _live_inbounds(
    panel_registry: PanelRegistry, panel_id: int
) -> list[dict]:
    """Inbounds straight from the panel.

    Raises `_PanelUnreachable` rather than returning an empty list, so callers
    never mistake a dead panel for a panel with no inbounds — the difference
    matters when deciding whether reseller rows are stale.
    """
    try:
        xui = panel_registry.get_client(panel_id)
        return await xui.list_inbounds()
    except PanelNotFoundError as e:
        raise _PanelUnreachable(str(e)) from e
    except (XuiError, httpx.HTTPError) as e:
        logger.warning("Panel #%s inbound fetch failed: %r", panel_id, e)
        raise _PanelUnreachable(_network_reason(e)) from e


def _inbound_ids(inbounds: list[dict]) -> set[int]:
    out: set[int] = set()
    for ib in inbounds:
        try:
            out.add(int(ib.get("id", ib.get("inboundId"))))
        except (TypeError, ValueError):
            continue
    return out


@router.callback_query(F.data == "pnl:noop")
async def panel_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.regexp(r"^pnl:bulk:\d+$"))
async def panel_bulk_pick_inbound(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    panel_id = int(callback.data.split(":", 2)[2])
    try:
        inbounds = await _live_inbounds(panel_registry, panel_id)
    except _PanelUnreachable as e:
        await callback.answer(await e.message(panel_id), show_alert=True)
        return
    if not inbounds:
        await callback.answer("اینبندی یافت نشد.", show_alert=True)
        return

    live = _inbound_ids(inbounds)
    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
        orphans = await orphan_inbound_ids(session, panel_id, live)
        coverage = {
            ib_id: await count_resellers_with_inbound(session, panel_id, ib_id)
            for ib_id in live | set(orphans)
        }
    total = next(iter(coverage.values()), (0, 0))[1]
    if total == 0:
        await callback.answer(t.BULK_INBOUND_NO_RESELLERS, show_alert=True)
        return

    text = t.BULK_INBOUND_PICK.format(
        panel_name=panel.name if panel else f"#{panel_id}", total=total
    )
    if orphans:
        text += t.BULK_INBOUND_ORPHAN_NOTE.format(
            ids=", ".join(str(i) for i in orphans)
        )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=panel_bulk_inbounds_kb(panel_id, inbounds, coverage, orphans),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^pnl:bulk:pick:\d+:\d+$"))
async def panel_bulk_confirm(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    _, _, _, panel_id_s, inbound_id_s = callback.data.split(":")
    panel_id, inbound_id = int(panel_id_s), int(inbound_id_s)

    try:
        live = _inbound_ids(await _live_inbounds(panel_registry, panel_id))
    except _PanelUnreachable as e:
        await callback.answer(await e.message(panel_id), show_alert=True)
        return

    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
        have, total = await count_resellers_with_inbound(
            session, panel_id, inbound_id
        )
    panel_name = panel.name if panel else f"#{panel_id}"
    # An inbound the panel no longer has can only be cleared, never handed out.
    # Otherwise: everyone already has it -> remove; anyone missing it -> add.
    is_orphan = inbound_id not in live
    enable = False if is_orphan else have < total
    if is_orphan:
        text = t.BULK_INBOUND_CONFIRM_ORPHAN.format(
            inbound_id=inbound_id, panel_name=panel_name, have=have
        )
    elif enable:
        text = t.BULK_INBOUND_CONFIRM_ADD.format(
            inbound_id=inbound_id,
            panel_name=panel_name,
            have=have,
            missing=total - have,
        )
    else:
        text = t.BULK_INBOUND_CONFIRM_REMOVE.format(
            inbound_id=inbound_id, panel_name=panel_name, have=have
        )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=panel_bulk_confirm_kb(panel_id, inbound_id, enable=enable),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^pnl:bulk:go:\d+:\d+:(on|off)$"))
async def panel_bulk_apply(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    _, _, _, panel_id_s, inbound_id_s, action = callback.data.split(":")
    panel_id, inbound_id = int(panel_id_s), int(inbound_id_s)
    enable = action == "on"

    async with get_session_factory()() as session:
        result = await apply_bulk_inbound(
            session, panel_id, inbound_id, enable=enable
        )

    title = (
        t.BULK_INBOUND_TITLE_ADD if enable else t.BULK_INBOUND_TITLE_REMOVE
    ).format(inbound_id=inbound_id)
    lines = [
        t.BULK_INBOUND_DONE.format(
            title=title,
            changed=result.changed,
            skipped_count=len(result.skipped),
        )
    ]
    if result.skipped:
        lines.append(t.BULK_INBOUND_SKIPPED_HEADER)
        for label, reason in result.skipped[:15]:
            lines.append(f"• {label}\n  {reason}")
    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=panel_view_kb(panel_id, is_active=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:health:"))
async def panel_inbound_health(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    panel_id = int(callback.data.split(":", 2)[2])
    try:
        inbounds = await _live_inbounds(panel_registry, panel_id)
    except _PanelUnreachable as e:
        # Never report resellers as broken when the panel itself is down.
        await callback.message.answer(await e.message(panel_id))  # type: ignore[union-attr]
        await callback.answer()
        return

    live = _inbound_ids(inbounds)
    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(panel_id)
        problems = await diagnose_panel_inbounds(session, panel_id, live)

    lines = [
        t.INBOUND_HEALTH_HEADER.format(
            panel_name=panel.name if panel else f"#{panel_id}",
            live=", ".join(str(i) for i in sorted(live)) or "—",
        )
    ]
    if not problems:
        lines.append(t.INBOUND_HEALTH_OK)
    else:
        lines.append(t.INBOUND_HEALTH_PROBLEM_HEADER)
        for d in problems[:20]:
            lines.append(f"\n{d.label}")
            if d.missing_allowed:
                lines.append(
                    t.INBOUND_HEALTH_MISSING_ALLOWED.format(
                        ids=", ".join(str(i) for i in d.missing_allowed)
                    )
                )
            if d.missing_attach:
                lines.append(
                    t.INBOUND_HEALTH_MISSING_ATTACH.format(
                        ids=", ".join(str(i) for i in d.missing_attach)
                    )
                )
            if d.fully_blocked:
                lines.append(t.INBOUND_HEALTH_BLOCKED)
        lines.append(t.INBOUND_HEALTH_HINT)

    await callback.message.answer("\n".join(lines))  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:inbounds:"))
async def panel_list_inbounds(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    try:
        inbounds = await _live_inbounds(panel_registry, panel_id)
    except _PanelUnreachable as e:
        await callback.answer(await e.message(panel_id), show_alert=True)
        return
    if not inbounds:
        await callback.answer("اینبندی یافت نشد.", show_alert=True)
        return
    lines = []
    for ib in inbounds[:30]:
        ib_id = ib.get("id", ib.get("inboundId", "?"))
        protocol = ib.get("protocol", "—")
        port = ib.get("port", "—")
        remark = ib.get("remark") or ib.get("tag") or ""
        lines.append(f"• id={ib_id} | {protocol} | port={port} | {remark}")
    await callback.message.answer(  # type: ignore[union-attr]
        f"اینباندهای پنل #{panel_id}:\n\n" + "\n".join(lines)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:del:"))
async def panel_delete_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        row = await PanelRepository(session).get(panel_id)
    if not row:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(
        t.PANEL_DELETE_CONFIRM.format(id=panel_id, name=row.name),
        reply_markup=panel_delete_confirm_kb(panel_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pnl:del_yes:"))
async def panel_delete_yes(
    callback: CallbackQuery, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        return
    panel_id = int(callback.data.split(":", 2)[2])
    async with get_session_factory()() as session:
        repo = PanelRepository(session)
        try:
            deleted = await repo.delete(panel_id)
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return
    if not deleted:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return
    async with get_session_factory()() as session:
        await panel_registry.reload_panel(session, panel_id)
    await callback.answer(t.PANEL_DELETED.format(id=panel_id))
    await _edit_panel_hub(callback.message)  # type: ignore[arg-type]
