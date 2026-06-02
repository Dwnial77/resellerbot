import re
from typing import NamedTuple

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import get_settings
from bot.keyboards.common import admin_main_kb
from bot.keyboards import labels as btn
from bot.texts import fa as t
from db.repository import PanelRepository, ResellerRepository
from services.panel_registry import PanelNotFoundError, PanelRegistry
from db.session import get_session_factory
from services.quota import QuotaService
from services.reseller_edit import (
    ResellerNotFoundError,
    apply_allowed_inbounds,
    apply_attach_inbounds,
    apply_display_name,
    apply_max_clients,
    apply_quota,
    clear_max_clients_limit,
)
from services.reseller_labels import (
    InvalidDisplayNameError,
    normalize_display_name,
    reseller_label,
)

router = Router()

_ADD_RESELLER_PATTERN = re.compile(r"^\d+\s+\S+\s+\d")


class AddResellerParsed(NamedTuple):
    telegram_id: int
    display_name: str | None
    panel_id: int
    quota_gb: float
    inbound_ids: list[int]


def _is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in get_settings().admin_telegram_ids


def _parse_add_reseller(text: str) -> AddResellerParsed:
    parts = text.split()
    if len(parts) < 3:
        raise ValueError("not enough parts")
    tg_id = int(parts[0])
    _MAX_PANEL_ID_HEURISTIC = 64

    # id panel_id quota inbounds (panel id is a small integer)
    if len(parts) >= 4:
        try:
            panel_id = int(parts[1])
            if 1 <= panel_id <= _MAX_PANEL_ID_HEURISTIC:
                quota_gb = float(parts[2].replace(",", "."))
                inbound_ids = [int(x) for x in parts[3:]]
                if inbound_ids:
                    return AddResellerParsed(
                        tg_id, None, panel_id, quota_gb, inbound_ids
                    )
        except ValueError:
            pass

    # Legacy: id quota inbounds -> panel 1
    try:
        quota_gb = float(parts[1].replace(",", "."))
        inbound_ids = [int(x) for x in parts[2:]]
        if inbound_ids:
            return AddResellerParsed(tg_id, None, 1, quota_gb, inbound_ids)
    except ValueError:
        pass

    # id name panel_id quota inbounds (needs at least 5 parts)
    if len(parts) >= 5:
        try:
            display_name = normalize_display_name(parts[1])
            panel_id = int(parts[2])
            if 1 <= panel_id <= _MAX_PANEL_ID_HEURISTIC:
                quota_gb = float(parts[3].replace(",", "."))
                inbound_ids = [int(x) for x in parts[4:]]
                if inbound_ids:
                    return AddResellerParsed(
                        tg_id, display_name, panel_id, quota_gb, inbound_ids
                    )
        except (ValueError, InvalidDisplayNameError):
            pass

    # Legacy named: id name quota inbounds -> panel 1
    display_name = normalize_display_name(parts[1])
    quota_gb = float(parts[2].replace(",", "."))
    inbound_ids = [int(x) for x in parts[3:]]
    if not inbound_ids:
        raise ValueError("no inbounds")
    return AddResellerParsed(tg_id, display_name, 1, quota_gb, inbound_ids)


@router.message(F.text == btn.ADMIN_HELP)
@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer(t.ADMIN_MENU, parse_mode="Markdown", reply_markup=admin_main_kb())


@router.message(F.text.regexp(_ADD_RESELLER_PATTERN))
async def add_reseller_inline(
    message: Message, panel_registry: PanelRegistry
) -> None:
    """Format: telegram_id quota_gb inbound... OR telegram_id name quota_gb inbound..."""
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        parsed = _parse_add_reseller(message.text or "")  # type: ignore[arg-type]
    except (ValueError, InvalidDisplayNameError):
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        panel = await PanelRepository(session).get(parsed.panel_id)
        if not panel:
            await message.answer(t.PANEL_NOT_FOUND)
            return
        if not panel.is_active:
            await message.answer(
                t.PANEL_INACTIVE_FOR_RESELLER.format(
                    panel_name=panel.name, panel_id=parsed.panel_id
                )
            )
            return
        repo = ResellerRepository(session)
        row = await repo.upsert(
            parsed.telegram_id,
            gb_to_bytes(parsed.quota_gb),
            parsed.inbound_ids,
            panel_id=parsed.panel_id,
            attach_inbound_ids=parsed.inbound_ids,
            display_name=parsed.display_name,
        )
        await panel_registry.reload_panel(session, parsed.panel_id)

    ids_s = ", ".join(str(i) for i in parsed.inbound_ids)
    await message.answer(
        t.RESELLER_ADDED.format(
            label=reseller_label(row),
            panel_id=parsed.panel_id,
            panel_name=panel.name,
            quota_gb=parsed.quota_gb,
            allowed_inbounds=ids_s,
            attach_inbounds=ids_s,
        )
    )


@router.message(Command("set_quota"))
async def set_quota(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("فرمت: /set_quota TELEGRAM_ID QUOTA_GB")
        return
    try:
        tg_id = int(parts[1])
        quota_gb = float(parts[2])
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_quota(session, tg_id, quota_gb)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
    await message.answer(result.message_text)


@router.message(Command("set_name"))
async def set_name(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("فرمت: /set_name TELEGRAM_ID NAME")
        return
    try:
        tg_id = int(parts[1])
        display_name = normalize_display_name(parts[2])
    except (ValueError, InvalidDisplayNameError):
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_display_name(session, tg_id, display_name)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
    await message.answer(result.message_text)


@router.message(Command("set_max_clients"))
async def set_max_clients_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("فرمت: /set_max_clients TELEGRAM_ID COUNT")
        return
    try:
        tg_id = int(parts[1])
        max_clients = int(parts[2])
        if max_clients < 1:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_max_clients(session, tg_id, max_clients)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
    await message.answer(result.message_text)


@router.message(Command("clear_max_clients"))
async def clear_max_clients_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("فرمت: /clear_max_clients TELEGRAM_ID")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await clear_max_clients_limit(session, tg_id)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
    await message.answer(result.message_text)


@router.message(Command("set_allowed_inbounds"))
async def set_allowed_inbounds_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("فرمت: /set_allowed_inbounds TELEGRAM_ID inbound_id...")
        return
    try:
        tg_id = int(parts[1])
        inbound_ids = [int(x) for x in parts[2:]]
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_allowed_inbounds(session, tg_id, inbound_ids)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
        except ValueError as e:
            await message.answer(str(e))
            return
    await message.answer(result.message_text)


@router.message(Command("set_attach_inbounds"))
async def set_attach_inbounds_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("فرمت: /set_attach_inbounds TELEGRAM_ID inbound_id...")
        return
    try:
        tg_id = int(parts[1])
        inbound_ids = [int(x) for x in parts[2:]]
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return

    async with get_session_factory()() as session:
        try:
            result = await apply_attach_inbounds(session, tg_id, inbound_ids)
        except ResellerNotFoundError:
            await message.answer("ریسلر یافت نشد.")
            return
        except ValueError as e:
            await message.answer(str(e))
            return
    await message.answer(result.message_text)


@router.message(Command("list_inbounds"))
async def list_inbounds_cmd(
    message: Message, panel_registry: PanelRegistry
) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    panel_id = 1
    if len(parts) >= 2:
        try:
            panel_id = int(parts[1])
        except ValueError:
            await message.answer("فرمت: /list_inbounds PANEL_ID")
            return
    try:
        xui = panel_registry.get_client(panel_id)
    except PanelNotFoundError as e:
        await message.answer(str(e))
        return
    try:
        inbounds = await xui.list_inbounds()
    except Exception as e:
        await message.answer(f"خطا در دریافت اینباندها: {e}")
        return
    if not inbounds:
        await message.answer("اینبندی در پنل یافت نشد.")
        return
    lines = []
    for ib in inbounds:
        ib_id = ib.get("id", ib.get("inboundId", "?"))
        protocol = ib.get("protocol", "—")
        port = ib.get("port", "—")
        remark = ib.get("remark") or ib.get("tag") or ""
        remark_part = f" — {remark}" if remark else ""
        lines.append(f"• id={ib_id} | {protocol} | port={port}{remark_part}")
    await message.answer(
        f"اینباندهای پنل #{panel_id}:\n\n" + "\n".join(lines)
    )


@router.message(Command("disable"))
async def disable_reseller(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("فرمت: /disable TELEGRAM_ID")
        return
    tg_id = int(parts[1])
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        row = await repo.set_active(tg_id, False)
    if row:
        await message.answer(t.RESELLER_DISABLED.format(label=reseller_label(row)))
    else:
        await message.answer("ریسلر یافت نشد.")


@router.message(Command("enable"))
async def enable_reseller(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("فرمت: /enable TELEGRAM_ID")
        return
    tg_id = int(parts[1])
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        row = await repo.set_active(tg_id, True)
    if row:
        await message.answer(t.RESELLER_ENABLED.format(label=reseller_label(row)))
    else:
        await message.answer("ریسلر یافت نشد.")


