import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import Panel, Reseller
from services.set_panel import (
    PanelNotFoundError,
    ResellerNotFoundError,
    SetPanelBlockedError,
    apply_reseller_panel,
)


def _reseller(panel_id: int = 1, tg_id: int = 100) -> Reseller:
    return Reseller(
        telegram_id=tg_id,
        panel_id=panel_id,
        quota_bytes=0,
        allowed_inbound_ids="1",
    )


def _panel(panel_id: int = 2, name: str = "p2") -> Panel:
    return Panel(
        id=panel_id,
        name=name,
        base_url="https://x",
        api_token="t",
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=True,
    )


def test_apply_unchanged_same_panel() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=2)
        panel = _panel(panel_id=2)

        with (
            patch("services.set_panel.PanelRepository") as PanelRepo,
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
        ):
            panel_repo = PanelRepo.return_value
            panel_repo.get = AsyncMock(return_value=panel)
            reseller_repo = ResellerRepo.return_value
            reseller_repo.get = AsyncMock(return_value=reseller)

            result = await apply_reseller_panel(session, 100, 2)

        assert result.unchanged is True
        assert result.reseller is reseller
        reseller_repo.client_count.assert_not_called()
        reseller_repo.set_panel_id.assert_not_called()

    asyncio.run(_run())


def test_apply_blocked_when_has_clients() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)
        panel = _panel(panel_id=2)

        with (
            patch("services.set_panel.PanelRepository") as PanelRepo,
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
        ):
            panel_repo = PanelRepo.return_value
            panel_repo.get = AsyncMock(return_value=panel)
            reseller_repo = ResellerRepo.return_value
            reseller_repo.get = AsyncMock(return_value=reseller)
            reseller_repo.client_count = AsyncMock(return_value=3)

            with pytest.raises(SetPanelBlockedError) as exc:
                await apply_reseller_panel(session, 100, 2)

        assert exc.value.client_count == 3
        reseller_repo.set_panel_id.assert_not_called()

    asyncio.run(_run())


def test_apply_success_zero_clients() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)
        updated = _reseller(panel_id=2)
        panel = _panel(panel_id=2)

        with (
            patch("services.set_panel.PanelRepository") as PanelRepo,
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
        ):
            panel_repo = PanelRepo.return_value
            panel_repo.get = AsyncMock(return_value=panel)
            reseller_repo = ResellerRepo.return_value
            reseller_repo.get = AsyncMock(return_value=reseller)
            reseller_repo.client_count = AsyncMock(return_value=0)
            reseller_repo.set_panel_id = AsyncMock(return_value=updated)

            result = await apply_reseller_panel(session, 100, 2)

        assert result.unchanged is False
        assert result.reseller.panel_id == 2
        reseller_repo.set_panel_id.assert_awaited_once_with(100, 2)

    asyncio.run(_run())


def test_apply_reseller_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()
        panel = _panel()

        with (
            patch("services.set_panel.PanelRepository") as PanelRepo,
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
        ):
            PanelRepo.return_value.get = AsyncMock(return_value=panel)
            ResellerRepo.return_value.get = AsyncMock(return_value=None)

            with pytest.raises(ResellerNotFoundError):
                await apply_reseller_panel(session, 100, 2)

    asyncio.run(_run())


def test_apply_panel_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()

        with patch("services.set_panel.PanelRepository") as PanelRepo:
            PanelRepo.return_value.get = AsyncMock(return_value=None)

            with pytest.raises(PanelNotFoundError):
                await apply_reseller_panel(session, 100, 2)

    asyncio.run(_run())
