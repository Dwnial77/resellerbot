"""Tests for admin panel edit service and keyboard."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from bot.keyboards.common import panel_edit_menu_kb
from db.models import Panel
from services.panel_edit import (
    PanelConnectionError,
    PanelNotFoundError,
    apply_panel_api_token,
    apply_panel_base_url,
    apply_panel_name,
    apply_panel_sub_public_url,
)


def _panel(
    panel_id: int = 1,
    *,
    base_url: str = "https://panel.example.com:2053",
    api_token: str = "secret-token",
) -> Panel:
    return Panel(
        id=panel_id,
        name="Test Panel",
        base_url=base_url,
        api_token=api_token,
        username=None,
        password=None,
        sub_public_url=None,
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=True,
    )


def test_panel_edit_menu_kb_callbacks_under_64_bytes() -> None:
    kb = panel_edit_menu_kb(99)
    for row in kb.inline_keyboard:
        for btn in row:
            assert btn.callback_data is not None
            assert len(btn.callback_data) < 64


def test_apply_panel_name() -> None:
    async def _run() -> None:
        session = AsyncMock()
        panel = _panel()
        updated = _panel()
        updated.name = "New Name"
        repo = AsyncMock()
        repo.get = AsyncMock(return_value=panel)
        repo.update_name = AsyncMock(return_value=updated)

        with patch("services.panel_edit.PanelRepository", return_value=repo):
            result = await apply_panel_name(session, 1, "New Name")

        assert result.panel.name == "New Name"
        assert "New Name" in result.message_text

    asyncio.run(_run())


def test_apply_panel_base_url_success() -> None:
    async def _run() -> None:
        session = AsyncMock()
        panel = _panel()
        updated = _panel(base_url="https://new.example.com:2053")
        repo = AsyncMock()
        repo.get = AsyncMock(return_value=panel)
        repo.update_base_url = AsyncMock(return_value=updated)

        with (
            patch("services.panel_edit.PanelRepository", return_value=repo),
            patch(
                "services.panel_edit._test_panel_connection",
                new_callable=AsyncMock,
            ),
        ):
            result = await apply_panel_base_url(
                session, 1, "https://new.example.com:2053"
            )

        repo.update_base_url.assert_awaited_once()
        assert "new.example.com" in result.message_text

    asyncio.run(_run())


def test_apply_panel_base_url_auth_failure() -> None:
    async def _run() -> None:
        session = AsyncMock()
        panel = _panel()
        repo = AsyncMock()
        repo.get = AsyncMock(return_value=panel)

        with (
            patch("services.panel_edit.PanelRepository", return_value=repo),
            patch(
                "services.panel_edit._test_panel_connection",
                new_callable=AsyncMock,
                side_effect=PanelConnectionError("auth failed"),
            ),
        ):
            with pytest.raises(PanelConnectionError):
                await apply_panel_base_url(session, 1, "https://bad.example.com:2053")

        repo.update_base_url.assert_not_called()

    asyncio.run(_run())


def test_apply_panel_api_token_success() -> None:
    async def _run() -> None:
        session = AsyncMock()
        panel = _panel()
        updated = _panel(api_token="new-token")
        repo = AsyncMock()
        repo.get = AsyncMock(return_value=panel)
        repo.update_api_token = AsyncMock(return_value=updated)

        with (
            patch("services.panel_edit.PanelRepository", return_value=repo),
            patch(
                "services.panel_edit._test_panel_connection",
                new_callable=AsyncMock,
            ),
        ):
            result = await apply_panel_api_token(session, 1, "new-token")

        repo.update_api_token.assert_awaited_once_with(1, "new-token")
        assert "new-token" not in result.message_text

    asyncio.run(_run())


def test_apply_panel_sub_public_url_clear() -> None:
    async def _run() -> None:
        session = AsyncMock()
        updated = _panel()
        updated.sub_public_url = None
        repo = AsyncMock()
        repo.update_sub_public_url = AsyncMock(return_value=updated)

        with patch("services.panel_edit.PanelRepository", return_value=repo):
            result = await apply_panel_sub_public_url(session, 1, None)

        repo.update_sub_public_url.assert_awaited_once_with(1, None)
        assert "—" in result.message_text

    asyncio.run(_run())


def test_apply_panel_name_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()
        repo = AsyncMock()
        repo.update_name = AsyncMock(return_value=None)

        with patch("services.panel_edit.PanelRepository", return_value=repo):
            with pytest.raises(PanelNotFoundError):
                await apply_panel_name(session, 99, "x")

    asyncio.run(_run())
