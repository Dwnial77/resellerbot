"""Admin: database backup and restore."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    backup_confirm_kb,
    backup_list_kb,
    backup_menu_kb,
)
from bot.states import BackupRestoreStates
from bot.texts import fa as t
from services.backup import (
    BackupError,
    clear_pending_restore,
    create_backup_bytes,
    list_backups,
    load_pending_restore_meta,
    project_root,
    save_pending_restore,
)
from services.updater import request_service_restart

router = Router()

_list_cache: dict[int, list] = {}


def _is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in get_settings().admin_telegram_ids


def _max_mb() -> int:
    return get_settings().backup_max_bytes // (1024 * 1024)


async def _show_backup_menu(message: Message) -> None:
    await message.answer(
        t.BACKUP_MENU.format(max_mb=_max_mb()),
        reply_markup=backup_menu_kb(),
    )


async def _show_restore_ready(
    message: Message,
    *,
    filename: str,
    size_bytes: int,
    edit: bool = False,
) -> None:
    text = t.BACKUP_RESTORE_READY.format(
        filename=filename,
        size_mb=size_bytes / (1024 * 1024),
    )
    markup = backup_confirm_kb()
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.message(Command("backup"))
@router.message(F.text == btn.BACKUP)
async def backup_start(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    await state.clear()
    await _show_backup_menu(message)


@router.callback_query(F.data == "bkp:menu")
async def backup_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.BACKUP_MENU.format(max_mb=_max_mb()),
            reply_markup=backup_menu_kb(),
        )
    await callback.answer()


@router.callback_query(F.data == "bkp:cancel_menu")
async def backup_cancel_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.BACKUP_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "bkp:create")
async def backup_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    if not callback.message:
        await callback.answer()
        return
    await state.clear()
    await callback.answer("در حال ساخت…")
    try:
        raw, filename = create_backup_bytes(project_root())
    except BackupError as e:
        await callback.message.edit_text(str(e))  # type: ignore[union-attr]
        return
    caption = t.BACKUP_CREATED_CAPTION.format(
        filename=filename,
        size_mb=len(raw) / (1024 * 1024),
    )
    await callback.message.answer_document(  # type: ignore[union-attr]
        BufferedInputFile(raw, filename=filename),
        caption=caption,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.BACKUP_MENU.format(max_mb=_max_mb()),
        reply_markup=backup_menu_kb(),
    )


@router.callback_query(F.data == "bkp:list")
async def backup_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    if not callback.message:
        await callback.answer()
        return
    await state.clear()
    entries = list_backups(project_root())
    if not entries:
        await callback.message.edit_text(t.BACKUP_LIST_EMPTY)  # type: ignore[union-attr]
        await callback.answer()
        return
    labels: list[tuple[int, str]] = []
    cached: list = []
    for index, entry in enumerate(entries[:10]):
        date_s = entry.modified_at.strftime("%Y-%m-%d %H:%M UTC")
        label = t.BACKUP_LIST_ITEM.format(
            name=entry.path.name,
            size_mb=entry.size_bytes / (1024 * 1024),
            date=date_s,
        )
        if len(label) > 60:
            label = label[:57] + "…"
        labels.append((index, label))
        cached.append(entry)
    _list_cache[callback.from_user.id] = cached
    await callback.message.edit_text(  # type: ignore[union-attr]
        t.BACKUP_LIST_HEADER,
        reply_markup=backup_list_kb(labels),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bkp:dl:"))
async def backup_download(callback: CallbackQuery) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    if not callback.message:
        await callback.answer()
        return
    try:
        index = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    except (IndexError, ValueError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    cached = _list_cache.get(callback.from_user.id, [])
    if index < 0 or index >= len(cached):
        await callback.answer("بک‌آپ یافت نشد. لیست را دوباره باز کنید.", show_alert=True)
        return
    entry = cached[index]
    raw = entry.path.read_bytes()
    await callback.message.answer_document(  # type: ignore[union-attr]
        BufferedInputFile(raw, filename=entry.path.name),
        caption=t.BACKUP_CREATED_CAPTION.format(
            filename=entry.path.name,
            size_mb=entry.size_bytes / (1024 * 1024),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "bkp:restore")
async def backup_restore_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(BackupRestoreStates.waiting_file)
    if callback.message:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t.BACKUP_RESTORE_PROMPT.format(max_mb=_max_mb()),
        )
    await callback.answer()


@router.message(BackupRestoreStates.waiting_file, F.document)
async def backup_restore_receive(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.document:
        return
    doc = message.document
    if doc.file_size and doc.file_size > get_settings().backup_max_bytes:
        await message.answer(t.BACKUP_TOO_LARGE)
        return
    name = (doc.file_name or "").lower()
    if not (name.endswith(".db") or name.endswith(".zip")):
        await message.answer(t.BACKUP_NOT_DB)
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
        meta = save_pending_restore(
            raw,
            uploaded_by=message.from_user.id,
            filename=doc.file_name or "backup.db",
            max_bytes=get_settings().backup_max_bytes,
            root=project_root(),
        )
    except BackupError as e:
        await message.answer(str(e))
        return

    await state.clear()
    await _show_restore_ready(
        message,
        filename=meta.filename,
        size_bytes=meta.size_bytes,
    )


@router.message(BackupRestoreStates.waiting_file)
async def backup_restore_waiting_invalid(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    await message.answer(t.BACKUP_NOT_DB)


@router.callback_query(F.data == "bkp:cancel")
async def backup_restore_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    clear_pending_restore(project_root())
    if callback.message:
        await callback.message.edit_text(t.BACKUP_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "bkp:apply")
async def backup_restore_apply(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    meta = load_pending_restore_meta(project_root())
    if not meta:
        await callback.answer(t.BACKUP_NO_PENDING, show_alert=True)
        return
    await state.clear()
    settings = get_settings()
    ok, detail = request_service_restart(settings.systemd_service_name)
    if callback.message:
        if ok:
            await callback.message.edit_text(  # type: ignore[union-attr]
                t.BACKUP_RESTARTING.format(
                    service=settings.systemd_service_name,
                )
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                t.BACKUP_RESTART_MANUAL.format(
                    detail=detail,
                    service=settings.systemd_service_name,
                )
            )
    await callback.answer()
