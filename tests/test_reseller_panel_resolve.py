import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import Panel, Reseller
from services.panel_registry import PanelNotFoundError, PanelRegistry, xui_client_from_panel
from services.panel_resolve import (
    ResellerPanelReason,
    ResellerPanelUnavailableError,
    xui_for_reseller,
)


def _panel(panel_id: int = 2, *, active: bool = True) -> Panel:
    return Panel(
        id=panel_id,
        name="germany",
        base_url="https://de.example.com",
        api_token="tok",
        username=None,
        password=None,
        sub_public_url=None,
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=active,
    )


def _reseller(panel_id: int = 2) -> Reseller:
    return Reseller(
        telegram_id=5266810479,
        panel_id=panel_id,
        quota_bytes=0,
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def test_xui_for_reseller_reload_when_missing_from_cache() -> None:
    async def _run() -> None:
        panel = _panel(2)
        reseller = _reseller(2)
        reg = PanelRegistry()
        session = AsyncMock()

        with patch(
            "services.panel_resolve.PanelRepository"
        ) as PanelRepo:
            repo = PanelRepo.return_value
            repo.get = AsyncMock(return_value=panel)
            reg.reload_panel = AsyncMock()

            async def _reload(_session: object, pid: int) -> None:
                reg._clients[pid] = xui_client_from_panel(panel)

            reg.reload_panel.side_effect = _reload

            xui = await xui_for_reseller(reg, session, reseller)
            assert xui.base_url == panel.base_url
            reg.reload_panel.assert_awaited_once_with(session, 2)

    asyncio.run(_run())


def test_xui_for_reseller_inactive_panel() -> None:
    async def _run() -> None:
        panel = _panel(2, active=False)
        reseller = _reseller(2)
        reg = PanelRegistry()
        session = AsyncMock()

        with patch("services.panel_resolve.PanelRepository") as PanelRepo:
            PanelRepo.return_value.get = AsyncMock(return_value=panel)
            with pytest.raises(ResellerPanelUnavailableError) as exc:
                await xui_for_reseller(reg, session, reseller)
        assert exc.value.reason == ResellerPanelReason.INACTIVE
        assert exc.value.panel_id == 2

    asyncio.run(_run())


def test_xui_for_reseller_not_loaded_after_reload() -> None:
    async def _run() -> None:
        panel = _panel(2)
        reseller = _reseller(2)
        reg = PanelRegistry()
        session = AsyncMock()

        with patch("services.panel_resolve.PanelRepository") as PanelRepo:
            PanelRepo.return_value.get = AsyncMock(return_value=panel)
            reg.reload_panel = AsyncMock()

            with pytest.raises(ResellerPanelUnavailableError) as exc:
                await xui_for_reseller(reg, session, reseller)
        assert exc.value.reason == ResellerPanelReason.NOT_LOADED

    asyncio.run(_run())


def test_xui_for_reseller_uses_cache_without_reload() -> None:
    panel = _panel(1)
    reg = PanelRegistry()
    reg._clients[1] = xui_client_from_panel(panel)
    reseller = _reseller(1)

    async def _run() -> None:
        session = AsyncMock()
        with patch("services.panel_resolve.PanelRepository") as PanelRepo:
            PanelRepo.return_value.get = AsyncMock(return_value=panel)
            reg.reload_panel = AsyncMock()
            xui = await xui_for_reseller(reg, session, reseller)
            assert xui is reg.get_client(1)
            reg.reload_panel.assert_not_called()

    asyncio.run(_run())
