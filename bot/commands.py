"""Register Telegram bot command menu (shown when user types /)."""

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

logger = logging.getLogger(__name__)

RESELLER_COMMANDS = [
    BotCommand(command="start", description="شروع و وضعیت حساب"),
]

ADMIN_COMMANDS = [
    BotCommand(command="admin", description="راهنمای کوتاه ادمین"),
    BotCommand(command="version", description="نسخه ربات"),
    BotCommand(command="bot_update", description="آپدیت ربات با ZIP"),
    BotCommand(command="list_resellers", description="هاب مدیریت ریسلرها"),
    BotCommand(command="set_quota", description="تغییر سقف حجم (آیدی و GB)"),
    BotCommand(command="set_max_clients", description="سقف تعداد سرویس"),
    BotCommand(command="clear_max_clients", description="حذف محدودیت تعداد سرویس"),
    BotCommand(command="set_name", description="نام نمایشی ریسلر"),
    BotCommand(command="set_allowed_inbounds", description="اینباندهای مجاز ریسلر"),
    BotCommand(command="set_attach_inbounds", description="اینباندهای متصل هنگام ساخت"),
    BotCommand(command="list_inbounds", description="لیست اینباندها از پنل"),
    BotCommand(command="panels", description="مدیریت پنل‌های 3x-ui"),
    BotCommand(command="templates", description="مدیریت قالب‌های ساخت سرویس"),
    BotCommand(command="add_template", description="ویزارد افزودن قالب"),
    BotCommand(command="set_panel", description="ویزارد تغییر پنل ریسلر"),
    BotCommand(command="disable", description="غیرفعال کردن ریسلر"),
    BotCommand(command="enable", description="فعال کردن ریسلر"),
    BotCommand(command="start", description="شروع و وضعیت حساب"),
]


async def setup_bot_commands(bot: Bot, admin_ids: list[int]) -> None:
    await bot.set_my_commands(RESELLER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in admin_ids:
        await bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    logger.info(
        "Bot commands registered (default + %d admin scope(s))",
        len(admin_ids),
    )
