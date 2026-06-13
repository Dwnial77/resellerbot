"""Admin broadcast message to all active resellers."""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import broadcast_confirm_kb
from bot.states import BroadcastStates
from bot.texts import fa as t
from db.repository import ResellerRepository
from db.session import get_session_factory
from services.broadcast import TELEGRAM_MESSAGE_MAX_LEN, broadcast_text_to_resellers

router = Router()

_PREVIEW_MAX = 500


def _preview_text(text: str) -> str:
    if len(text) <= _PREVIEW_MAX:
        return text
    return text[: _PREVIEW_MAX - 3] + "..."


@router.message(F.text == btn.BROADCAST)
@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await state.set_state(BroadcastStates.message)
    await message.answer(t.BROADCAST_PROMPT)


@router.message(BroadcastStates.message)
async def broadcast_compose(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer(t.BROADCAST_EMPTY)
        return
    if len(text) > TELEGRAM_MESSAGE_MAX_LEN:
        await message.answer(t.BROADCAST_TOO_LONG)
        return

    async with get_session_factory()() as session:
        resellers = await ResellerRepository(session).list_active()
    if not resellers:
        await state.clear()
        await message.answer(t.BROADCAST_NO_RECIPIENTS)
        return

    await state.update_data(broadcast_text=text, recipient_count=len(resellers))
    await state.set_state(BroadcastStates.confirm)
    await message.answer(
        t.BROADCAST_CONFIRM.format(
            count=len(resellers),
            preview=_preview_text(text),
        ),
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(BroadcastStates.confirm, F.data == "bc_confirm")
async def broadcast_confirm(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await state.clear()
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        resellers = await ResellerRepository(session).list_active()
    if not resellers:
        await state.clear()
        await callback.message.edit_text(t.BROADCAST_NO_RECIPIENTS)  # type: ignore[union-attr]
        await callback.answer()
        return

    await callback.message.edit_text("در حال ارسال پیام همگانی…")  # type: ignore[union-attr]
    await callback.answer()
    result = await broadcast_text_to_resellers(bot, resellers, text)
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.BROADCAST_DONE.format(
            sent=result.sent,
            failed=result.failed,
            blocked=result.blocked,
        )
    )


@router.callback_query(BroadcastStates.confirm, F.data == "bc_cancel")
@router.message(BroadcastStates.message, Command("cancel"))
@router.message(BroadcastStates.confirm, Command("cancel"))
async def broadcast_cancel(
    event: Message | CallbackQuery, state: FSMContext
) -> None:
    user_id = event.from_user.id if event.from_user else None
    if not _is_admin(user_id):
        return
    await state.clear()
    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.edit_text(t.BROADCAST_CANCELLED)  # type: ignore[union-attr]
        await event.answer()
    else:
        await event.answer(t.BROADCAST_CANCELLED)
