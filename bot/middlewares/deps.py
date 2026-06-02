from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.agent_debug import agent_log
from db.repository import PanelRepository, ResellerRepository
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
                panel_row = None
                if reseller is not None:
                    panel_row = await PanelRepository(session).get(reseller.panel_id)
            if reseller is not None:
                data["panel_id"] = reseller.panel_id
                loaded_ids = self.registry.loaded_panel_ids()
                # #region agent log
                agent_log(
                    location="deps.py:PanelMiddleware",
                    message="reseller panel resolve",
                    hypothesis_id="H1",
                    data={
                        "user_id": user.id,
                        "reseller_panel_id": reseller.panel_id,
                        "reseller_active": reseller.is_active,
                        "registry_loaded_ids": loaded_ids,
                        "panel_in_registry": reseller.panel_id in loaded_ids,
                        "db_panel_exists": panel_row is not None,
                        "db_panel_active": (
                            panel_row.is_active if panel_row is not None else None
                        ),
                    },
                )
                # #endregion
                try:
                    data["xui"] = self.registry.get_client(reseller.panel_id)
                    # #region agent log
                    agent_log(
                        location="deps.py:PanelMiddleware",
                        message="xui injected",
                        hypothesis_id="H5",
                        data={"user_id": user.id, "panel_id": reseller.panel_id},
                    )
                    # #endregion
                except PanelNotFoundError:
                    # #region agent log
                    agent_log(
                        location="deps.py:PanelMiddleware",
                        message="PanelNotFoundError, xui not set",
                        hypothesis_id="H1",
                        data={
                            "user_id": user.id,
                            "panel_id": reseller.panel_id,
                            "registry_loaded_ids": loaded_ids,
                        },
                    )
                    # #endregion
        return await handler(event, data)

