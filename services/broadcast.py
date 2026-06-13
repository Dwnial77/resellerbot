from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from db.models import Reseller

TELEGRAM_MESSAGE_MAX_LEN = 4096


@dataclass
class BroadcastResult:
    sent: int
    failed: int
    blocked: int


async def broadcast_text_to_resellers(
    bot: Bot,
    resellers: list[Reseller],
    text: str,
    *,
    delay_s: float = 0.05,
) -> BroadcastResult:
    sent = 0
    failed = 0
    blocked = 0
    for i, reseller in enumerate(resellers):
        if i > 0 and delay_s > 0:
            await asyncio.sleep(delay_s)
        try:
            await bot.send_message(chat_id=reseller.telegram_id, text=text)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            failed += 1
        except Exception:
            failed += 1
    return BroadcastResult(sent=sent, failed=failed, blocked=blocked)
