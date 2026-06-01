"""Admin: upload release ZIP and restart to apply update."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards.common import bot_update_confirm_kb
from bot.states import BotUpdateStates
from bot.texts import fa as t
from bot.version import __version__
from services.updater import (
    UpdateError,
    clear_pending,
    load_pending_meta,
    request_service_restart,
    save_pending_update,
)

logger = logging.getLogger(__name__)

router = Router()


def _is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in get_settings().admin_telegram_ids


@router.message(Command("bot_update"))
@router.message(Command("version"))
@router.message(F.text == "⬆️ آپدیت ربات")
async def bot_update_start(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/version"):
        await message.answer(t.VERSION_INFO.format(version=__version__))
        return
    await state.clear()
    await state.set_state(BotUpdateStates.waiting_zip)
    await message.answer(
        t.BOT_UPDATE_PROMPT.format(
            version=__version__,
            max_mb=get_settings().update_zip_max_bytes // (1024 * 1024),
        )
    )


@router.message(BotUpdateStates.waiting_zip, F.document)
async def bot_update_receive_zip(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.document:
        return
    doc = message.document
    if doc.file_size and doc.file_size > get_settings().update_zip_max_bytes:
        await message.answer(t.BOT_UPDATE_TOO_LARGE)
        return
    name = (doc.file_name or "").lower()
    if not name.endswith(".zip"):
        await message.answer(t.BOT_UPDATE_NOT_ZIP)
        return

    bot = message.bot
    assert bot is not None
    file = await bot.get_file(doc.file_id)
    if not file.file_path:
        await message.answer(t.INVALID_INPUT)
        return
    downloaded = await bot.download_file(file.file_path)
    if downloaded is None:
        await message.answer(t.INVALID_INPUT)
        return
    raw = downloaded.read()
    try:
        meta = save_pending_update(
            raw,
            uploaded_by=message.from_user.id,
            filename=doc.file_name or "update.zip",
            max_bytes=get_settings().update_zip_max_bytes,
            allow_downgrade=get_settings().allow_update_downgrade,
        )
    except UpdateError as e:
        await message.answer(str(e))
        return

    await state.clear()
    await message.answer(
        t.BOT_UPDATE_READY.format(
            current=__version__,
            target=meta.target_version,
            filename=meta.filename,
        ),
        reply_markup=bot_update_confirm_kb(),
    )


@router.message(BotUpdateStates.waiting_zip)
async def bot_update_waiting_invalid(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    await message.answer(t.BOT_UPDATE_NOT_ZIP)


@router.callback_query(F.data == "upd:cancel")
async def bot_update_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    clear_pending()
    if callback.message:
        await callback.message.edit_text(t.BOT_UPDATE_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "upd:apply")
async def bot_update_apply(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    meta = load_pending_meta()
    if not meta:
        await callback.answer(t.BOT_UPDATE_NO_PENDING, show_alert=True)
        return
    await state.clear()
    settings = get_settings()
    ok, detail = request_service_restart(settings.systemd_service_name)
    if callback.message:
        if ok:
            await callback.message.edit_text(  # type: ignore[union-attr]
                t.BOT_UPDATE_RESTARTING.format(
                    target=meta.target_version,
                    service=settings.systemd_service_name,
                )
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                t.BOT_UPDATE_RESTART_MANUAL.format(
                    target=meta.target_version,
                    detail=detail,
                    service=settings.systemd_service_name,
                )
            )
    await callback.answer()
