"""Admin wizard to change a reseller's assigned panel."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    set_panel_confirm_kb,
    set_panel_pick_panel_kb,
    set_panel_reseller_kb,
)
from bot.states import SetPanelStates
from bot.texts import fa as t
from db.repository import PanelRepository, ResellerRepository
from db.session import get_session_factory
from services.reseller_labels import reseller_label
from services.set_panel import (
    PanelNotFoundError,
    ResellerNotFoundError,
    SetPanelBlockedError,
    apply_reseller_panel,
)

router = Router()


async def _begin_set_panel_for_reseller(
    message: Message, state: FSMContext, tg_id: int
) -> None:
    async with get_session_factory()() as session:
        reseller_repo = ResellerRepository(session)
        panel_repo = PanelRepository(session)
        reseller = await reseller_repo.get(tg_id)
        if not reseller:
            await message.edit_text("ریسلر یافت نشد.")
            return
        client_count = await reseller_repo.client_count(tg_id)
        current_panel = await panel_repo.get(reseller.panel_id)
        current_name = current_panel.name if current_panel else f"#{reseller.panel_id}"

        if client_count > 0:
            await message.edit_text(
                t.PANEL_SET_BLOCKED_HAS_CLIENTS.format(
                    label=reseller_label(reseller),
                    client_count=client_count,
                )
            )
            await state.clear()
            return

        panels = await panel_repo.list_active()
        if not panels:
            await message.edit_text(t.PANEL_SET_NO_PANELS)
            await state.clear()
            return

    await state.update_data(
        reseller_tg_id=tg_id,
        old_panel_id=reseller.panel_id,
        old_panel_name=current_name,
        client_count=client_count,
        label=reseller_label(reseller),
    )
    await state.set_state(SetPanelStates.pick_panel)
    await message.edit_text(
        t.PANEL_SET_WIZARD_PICK_PANEL.format(
            label=reseller_label(reseller),
            current_panel_name=current_name,
            current_panel_id=reseller.panel_id,
            client_count=client_count,
        ),
        reply_markup=set_panel_pick_panel_kb(panels),
    )


async def _start_set_panel_wizard(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SetPanelStates.pick_reseller)
    async with get_session_factory()() as session:
        resellers = await ResellerRepository(session).list_all()
        panel_repo = PanelRepository(session)
        panel_names: dict[int, str] = {}
        for r in resellers:
            if r.panel_id not in panel_names:
                p = await panel_repo.get(r.panel_id)
                panel_names[r.panel_id] = p.name if p else f"#{r.panel_id}"

    if not resellers:
        await message.answer(t.PANEL_SET_NO_RESELLERS)
        await state.clear()
        return

    await message.answer(
        t.PANEL_SET_WIZARD_PICK_RESELLER,
        reply_markup=set_panel_reseller_kb(resellers, panel_names),
    )


async def _format_set_panel_success(
    session, telegram_id: int, panel_id: int, unchanged: bool
) -> str:
    reseller = await ResellerRepository(session).get(telegram_id)
    panel = await PanelRepository(session).get(panel_id)
    assert reseller is not None and panel is not None
    label = reseller_label(reseller)
    if unchanged:
        return t.PANEL_SET_UNCHANGED.format(
            label=label,
            panel_name=panel.name,
            panel_id=panel.id,
        )
    return t.PANEL_SET_FOR_RESELLER.format(
        label=label,
        panel_name=panel.name,
        panel_id=panel.id,
    )


@router.message(F.text == btn.SET_PANEL_RESELLER)
@router.message(Command("set_panel"))
async def set_panel_entry(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if message.text and message.text.strip().startswith("/set_panel") and len(parts) >= 3:
        try:
            tg_id = int(parts[1])
            panel_id = int(parts[2])
        except ValueError:
            await message.answer(t.INVALID_INPUT)
            return
        async with get_session_factory()() as session:
            try:
                result = await apply_reseller_panel(session, tg_id, panel_id)
            except PanelNotFoundError:
                await message.answer(t.PANEL_NOT_FOUND)
                return
            except ResellerNotFoundError:
                await message.answer("ریسلر یافت نشد.")
                return
            except SetPanelBlockedError as e:
                reseller = await ResellerRepository(session).get(tg_id)
                if reseller:
                    await message.answer(
                        t.PANEL_SET_BLOCKED_HAS_CLIENTS.format(
                            label=reseller_label(reseller),
                            client_count=e.client_count,
                        )
                    )
                return
            text = await _format_set_panel_success(
                session, tg_id, panel_id, result.unchanged
            )
        await message.answer(text)
        return

    await _start_set_panel_wizard(message, state)


@router.callback_query(F.data == "rpnl:cancel")
async def set_panel_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.PANEL_SET_WIZARD_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("rpnl:res:"))
async def set_panel_pick_reseller(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    if callback.message:
        await _begin_set_panel_for_reseller(
            callback.message, state, tg_id  # type: ignore[arg-type]
        )
    await callback.answer()


@router.callback_query(F.data.startswith("rsl:set_panel:"))
async def set_panel_from_reseller_hub(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 2)[2])
    await _begin_set_panel_for_reseller(callback.message, state, tg_id)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("rpnl:pan:"))
async def set_panel_pick_panel(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    panel_id = int(callback.data.split(":", 2)[2])
    data = await state.get_data()
    new_panel_id = panel_id

    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(new_panel_id)
    if not panel:
        await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
        return

    await state.update_data(new_panel_id=new_panel_id, new_panel_name=panel.name)
    await state.set_state(SetPanelStates.confirm)
    await callback.message.edit_text(
        t.PANEL_SET_WIZARD_CONFIRM.format(
            label=data.get("label", ""),
            old_panel_name=data.get("old_panel_name", ""),
            old_panel_id=data.get("old_panel_id", ""),
            new_panel_name=panel.name,
            new_panel_id=new_panel_id,
        ),
        reply_markup=set_panel_confirm_kb(),
    )
    await callback.answer()


@router.callback_query(SetPanelStates.confirm, F.data == "rpnl:save")
async def set_panel_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    tg_id = data.get("reseller_tg_id")
    panel_id = data.get("new_panel_id")
    if tg_id is None or panel_id is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_reseller_panel(session, int(tg_id), int(panel_id))
        except PanelNotFoundError:
            await callback.answer(t.PANEL_NOT_FOUND, show_alert=True)
            return
        except ResellerNotFoundError:
            await callback.answer("ریسلر یافت نشد.", show_alert=True)
            return
        except SetPanelBlockedError as e:
            await callback.answer(
                t.PANEL_SET_BLOCKED_HAS_CLIENTS.format(
                    label=data.get("label", ""),
                    client_count=e.client_count,
                ),
                show_alert=True,
            )
            return
        text = await _format_set_panel_success(
            session, int(tg_id), int(panel_id), result.unchanged
        )

    await state.clear()
    if callback.message:
        await callback.message.edit_text(text)
    await callback.answer()
