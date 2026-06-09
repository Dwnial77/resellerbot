from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import get_settings
from bot.keyboards.common import admin_main_kb, reseller_main_kb
from bot.texts import fa as t
from db.repository import ResellerRepository
from db.session import get_session_factory
from bot.utils.reseller_welcome import format_reseller_welcome

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    if message.from_user and message.from_user.id in settings.admin_telegram_ids:
        await message.answer(t.ADMIN_MENU, parse_mode="Markdown", reply_markup=admin_main_kb())
        return

    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(message.from_user.id)  # type: ignore[union-attr]
        if not reseller or not reseller.is_active:
            await message.answer(t.NOT_RESELLER)
            return
        welcome = await format_reseller_welcome(session, reseller)
    await message.answer(welcome, reply_markup=reseller_main_kb())


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    settings = get_settings()
    if not message.from_user or message.from_user.id not in settings.admin_telegram_ids:
        await message.answer("دسترسی ادمین ندارید.")
        return
    await message.answer(t.ADMIN_MENU, parse_mode="Markdown", reply_markup=admin_main_kb())
