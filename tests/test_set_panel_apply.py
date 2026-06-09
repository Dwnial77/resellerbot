import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import Panel, Reseller, ResellerPanel
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

    asyncio.run(_run())


def test_apply_blocked_when_not_assigned() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)

        with (
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
            patch(
                "services.set_panel.apply_set_default_panel",
                side_effect=__import__(
                    "services.reseller_panel_edit",
                    fromlist=["AssignmentNotFoundError"],
                ).AssignmentNotFoundError(),
            ),
        ):
            ResellerRepo.return_value.get = AsyncMock(return_value=reseller)

            with pytest.raises(SetPanelBlockedError) as exc:
                await apply_reseller_panel(session, 100, 2)

        assert exc.value.panel_id == 2

    asyncio.run(_run())


def test_apply_success_sets_default() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)
        updated = _reseller(panel_id=2)
        panel = _panel(panel_id=2)
        assignment = ResellerPanel(
            reseller_tg_id=100,
            panel_id=2,
            quota_bytes=0,
            lifetime_allocated_bytes=0,
            allowed_inbound_ids="[1]",
            is_active=True,
        )
        from services.reseller_panel_edit import PanelEditResult

        edit_result = PanelEditResult(
            assignment=assignment,
            panel=panel,
            message_text="ok",
        )

        with (
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
            patch(
                "services.set_panel.apply_set_default_panel",
                new_callable=AsyncMock,
                return_value=edit_result,
            ),
        ):
            reseller_repo = ResellerRepo.return_value
            reseller_repo.get = AsyncMock(side_effect=[reseller, updated])

            result = await apply_reseller_panel(session, 100, 2)

        assert result.unchanged is False
        assert result.reseller.panel_id == 2

    asyncio.run(_run())


def test_apply_reseller_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()

        with patch("services.set_panel.ResellerRepository") as ResellerRepo:
            ResellerRepo.return_value.get = AsyncMock(return_value=None)

            with pytest.raises(ResellerNotFoundError):
                await apply_reseller_panel(session, 100, 2)

    asyncio.run(_run())


def test_apply_panel_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)

        with (
            patch("services.set_panel.ResellerRepository") as ResellerRepo,
            patch(
                "services.set_panel.apply_set_default_panel",
                side_effect=__import__(
                    "services.reseller_panel_edit",
                    fromlist=["PanelNotFoundError"],
                ).PanelNotFoundError(),
            ),
        ):
            ResellerRepo.return_value.get = AsyncMock(return_value=reseller)

            with pytest.raises(PanelNotFoundError):
                await apply_reseller_panel(session, 100, 2)

    asyncio.run(_run())
