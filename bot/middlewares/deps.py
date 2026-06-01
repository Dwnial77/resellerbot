from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from db.repository import ResellerRepository
from db.session import get_session_factory
from services.panel_registry import PanelNotFoundError, PanelRegistry


def _event_user(event: TelegramObject) -> User | None:
    if isinstance(event, Message) and event.from_user:
        return event.from_user
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user
    return None


class PanelMiddleware(BaseMiddleware):
    def __init__(self, registry: PanelRegistry) -> None:
        self.registry = registry

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["panel_registry"] = self.registry
        user = _event_user(event)
        if user is not None:
            async with get_session_factory()() as session:
                reseller = await ResellerRepository(session).get(user.id)
            if reseller is not None:
                data["panel_id"] = reseller.panel_id
                try:
                    data["xui"] = self.registry.get_client(reseller.panel_id)
                except PanelNotFoundError:
                    pass
        return await handler(event, data)
