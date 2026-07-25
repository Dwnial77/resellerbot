"""Admin screen to configure the guest self-service sales channel."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    guest_config_hub_kb,
    guest_config_inbounds_kb,
    guest_config_pick_panel_kb,
    guest_main_kb,
)
from bot.states import GuestConfigStates
from bot.texts import fa as t
from db.repository import GuestSalesConfigRepository, PanelRepository, inbound_ids_from_json
from db.session import get_session_factory
from services.panel_registry import PanelNotFoundError, PanelRegistry

router = Router()


async def _hub_content() -> tuple[str, object]:
    async with get_session_factory()() as session:
        config = await GuestSalesConfigRepository(session).get_or_create()
        panel_label = "تنظیم نشده"
        if config.panel_id is not None:
            panel = await PanelRepository(session).get(config.panel_id)
            panel_label = f"#{config.panel_id} {panel.name}" if panel else f"#{config.panel_id}"
    inbound_ids = inbound_ids_from_json(config.inbound_ids)
    inbound_label = ", ".join(str(i) for i in inbound_ids) if inbound_ids else "تنظیم نشده"
    text = t.GUEST_CONFIG_HUB.format(
        status="فعال ✅" if config.is_enabled else "غیرفعال ⏸",
        panel_label=panel_label,
        inbound_label=inbound_label,
        card_number_label=config.card_number or "تنظیم نشده",
        card_holder_label=config.card_holder or "تنظیم نشده",
    )
    return text, guest_config_hub_kb(config)


async def _send_hub(target: Message) -> None:
    text, markup = await _hub_content()
    await target.answer(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_hub(target: Message) -> None:
    text, markup = await _hub_content()
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]


@router.message(F.text == btn.GUEST_SALES_SETTINGS)
async def guest_settings_hub(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await _send_hub(message)


@router.message(F.text == btn.PREVIEW_GUEST_MODE)
async def preview_guest_mode(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer(t.ADMIN_GUEST_PREVIEW_NOTE, reply_markup=guest_main_kb())


@router.callback_query(F.data == "gcfg:hub")
async def guest_settings_hub_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await _edit_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "gcfg:wiz_cancel")
async def guest_settings_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await _edit_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "gcfg:pick_panel")
async def guest_settings_pick_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    async with get_session_factory()() as session:
        panels = await PanelRepository(session).list_active()
    if not panels:
        await callback.answer(t.PANEL_SET_NO_PANELS, show_alert=True)
        return
    await state.set_state(GuestConfigStates.pick_panel)
    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.GUEST_CONFIG_PICK_PANEL,
            reply_markup=guest_config_pick_panel_kb(panels),
        )
    await callback.answer()


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
        reply_markup=guest_config_inbounds_kb(inbounds, selected)
    )


@router.callback_query(GuestConfigStates.pick_panel, F.data.startswith("gcfg:pan:"))
async def guest_settings_panel_picked(
    callback: CallbackQuery, state: FSMContext, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        panel_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    try:
        xui = panel_registry.get_client(panel_id)
        inbounds = await xui.list_inbounds()
    except (PanelNotFoundError, Exception) as e:
        await callback.message.edit_text(f"خطا در دریافت اینباندها: {e}")  # type: ignore[union-attr]
        await state.clear()
        await callback.answer()
        return
    if not inbounds:
        await callback.message.edit_text(t.RESELLER_WIZARD_INBOUNDS_EMPTY)  # type: ignore[union-attr]
        await state.clear()
        await callback.answer()
        return
    await state.update_data(panel_id=panel_id, selected_inbounds=[])
    await state.set_state(GuestConfigStates.pick_inbounds)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.GUEST_CONFIG_PICK_INBOUNDS,
        reply_markup=guest_config_inbounds_kb(inbounds, set()),
    )
    await callback.answer()


@router.callback_query(GuestConfigStates.pick_inbounds, F.data.startswith("gcfg:ib:t:"))
async def guest_settings_inbound_toggle(
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


@router.callback_query(GuestConfigStates.pick_inbounds, F.data == "gcfg:ib:done")
async def guest_settings_inbounds_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    panel_id = data.get("panel_id")
    selected = data.get("selected_inbounds") or []
    if not selected or panel_id is None:
        await callback.answer(t.RESELLER_WIZARD_INBOUNDS_NONE_SELECTED, show_alert=True)
        return
    async with get_session_factory()() as session:
        await GuestSalesConfigRepository(session).update(
            panel_id=int(panel_id), inbound_ids=list(selected)
        )
    await state.clear()
    await callback.answer(t.GUEST_CONFIG_SAVED)
    if callback.message:
        await _edit_hub(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "gcfg:card_number")
async def guest_settings_card_number_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.set_state(GuestConfigStates.card_number)
    if callback.message:
        await callback.message.edit_text(t.GUEST_CONFIG_CARD_NUMBER_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.message(GuestConfigStates.card_number)
async def guest_settings_card_number_input(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    card_number = (message.text or "").strip()
    if not card_number:
        await message.answer(t.INVALID_INPUT)
        return
    async with get_session_factory()() as session:
        await GuestSalesConfigRepository(session).update(card_number=card_number)
    await state.clear()
    await message.answer(t.GUEST_CONFIG_SAVED)
    await _send_hub(message)


@router.callback_query(F.data == "gcfg:card_holder")
async def guest_settings_card_holder_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.set_state(GuestConfigStates.card_holder)
    if callback.message:
        await callback.message.edit_text(t.GUEST_CONFIG_CARD_HOLDER_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.message(GuestConfigStates.card_holder)
async def guest_settings_card_holder_input(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    card_holder = (message.text or "").strip()
    if not card_holder:
        await message.answer(t.INVALID_INPUT)
        return
    async with get_session_factory()() as session:
        await GuestSalesConfigRepository(session).update(card_holder=card_holder)
    await state.clear()
    await message.answer(t.GUEST_CONFIG_SAVED)
    await _send_hub(message)


@router.callback_query(F.data == "gcfg:toggle")
async def guest_settings_toggle(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    async with get_session_factory()() as session:
        repo = GuestSalesConfigRepository(session)
        config = await repo.get_or_create()
        if not config.is_enabled:
            if not config.panel_id or not config.inbound_ids or not config.card_number:
                await callback.answer(t.GUEST_ORDER_NOT_CONFIGURED, show_alert=True)
                return
        await repo.update(is_enabled=not config.is_enabled)
    await callback.answer()
    if callback.message:
        await _edit_hub(callback.message)  # type: ignore[arg-type]
