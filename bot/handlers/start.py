from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import get_settings
from bot.keyboards.common import admin_main_kb, reseller_main_kb
from bot.texts import fa as t
from db.repository import PanelRepository, ResellerRepository, format_inbound_summary
from db.session import get_session_factory
from services.quota import QuotaService, format_max_clients_line

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
        panel = await PanelRepository(session).get(reseller.panel_id)
        panel_name = panel.name if panel else f"#{reseller.panel_id}"
        quota = QuotaService(repo)
        st = await quota.status(reseller)
        inbounds_summary = format_inbound_summary(reseller)
    display_name = f" {reseller.display_name}" if reseller.display_name else ""
    await message.answer(
        t.WELCOME_RESELLER.format(
            display_name=display_name,
            panel_id=reseller.panel_id,
            panel_name=panel_name,
            quota_gb=st.quota_gb,
            used_gb=st.used_gb,
            remaining_gb=st.remaining_gb,
            client_count=st.client_count,
            max_clients_line=format_max_clients_line(st),
            inbounds_summary=inbounds_summary,
        ),
        reply_markup=reseller_main_kb(),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    settings = get_settings()
    if not message.from_user or message.from_user.id not in settings.admin_telegram_ids:
        await message.answer("دسترسی ادمین ندارید.")
        return
    await message.answer(t.ADMIN_MENU, parse_mode="Markdown", reply_markup=admin_main_kb())
