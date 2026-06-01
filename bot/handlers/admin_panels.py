"""Admin hub and wizard for multiple 3x-ui panels."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.utils.panel_url import InvalidPanelUrlError, normalize_http_url, normalize_sub_public_url
from bot.keyboards.common import (
    panel_admin_hub_kb,
    panel_delete_confirm_kb,
    panel_view_kb,
    panel_wizard_confirm_kb,
    panel_wizard_skip_sub_kb,
)
from bot.states import AddPanelStates
from bot.texts import fa as t
from db.repository import PanelRepository
from db.session import get_session_factory
from services.panel_registry import PanelNotFoundError, PanelRegistry
from xui.client import XuiClient

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
        xui = panel_registry.get_client(panel_id)
        inbounds = await xui.list_inbounds()
    except (PanelNotFoundError, Exception) as e:
        await callback.answer(str(e)[:200], show_alert=True)
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
