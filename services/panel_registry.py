"""Cache of XuiClient instances per panel row."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Panel
from db.repository import PanelRepository
from xui.client import XuiClient

logger = logging.getLogger(__name__)


class PanelNotFoundError(Exception):
    pass


class PanelInactiveError(Exception):
    pass


def xui_client_from_panel(panel: Panel) -> XuiClient:
    return XuiClient(
        panel.base_url,
        api_token=panel.api_token,
        username=panel.username,
        password=panel.password,
        verify_ssl=panel.verify_ssl,
        sub_public_url=panel.sub_public_url,
        auto_vision_flow=panel.auto_vision_flow,
        auto_reseller_group=panel.auto_reseller_group,
    )


class PanelRegistry:
    def __init__(self) -> None:
        self._clients: dict[int, XuiClient] = {}

    async def load_from_db(self, session: AsyncSession) -> None:
        await self.close_all()
        panels = await PanelRepository(session).list_active()
        for panel in panels:
            self._clients[panel.id] = xui_client_from_panel(panel)
        logger.info("Panel registry loaded %d active panel(s)", len(self._clients))

    async def reload_panel(self, session: AsyncSession, panel_id: int) -> None:
        panel = await PanelRepository(session).get(panel_id)
        if panel is None or not panel.is_active:
            old = self._clients.pop(panel_id, None)
            if old is not None:
                await old.close()
            return
        old = self._clients.pop(panel_id, None)
        if old is not None:
            await old.close()
        self._clients[panel_id] = xui_client_from_panel(panel)

    def get_client(self, panel_id: int) -> XuiClient:
        client = self._clients.get(panel_id)
        if client is None:
            raise PanelNotFoundError(
                f"پنل #{panel_id} در دسترس نیست (غیرفعال یا ثبت نشده)."
            )
        return client

    def loaded_panel_ids(self) -> list[int]:
        return list(self._clients.keys())

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
