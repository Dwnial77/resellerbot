from collections import defaultdict
from collections.abc import Awaitable, Callable
from time import time
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.config import get_settings


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id not in get_settings().admin_telegram_ids:
            if isinstance(event, Message):
                await event.answer("دسترسی ادمین ندارید.")
            return None
        data["is_admin"] = True
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Simple per-user rate limit for create operations."""

    def __init__(self) -> None:
        self._hits: dict[int, list[float]] = defaultdict(list)

    def _check(self, user_id: int, limit: int, window: float = 60.0) -> bool:
        now = time()
        hits = [t for t in self._hits[user_id] if now - t < window]
        if len(hits) >= limit:
            self._hits[user_id] = hits
            return False
        hits.append(now)
        self._hits[user_id] = hits
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["rate_limit_check"] = self._check
        return await handler(event, data)
