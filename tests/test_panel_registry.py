from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import Panel
from services.panel_registry import PanelNotFoundError, PanelRegistry, xui_client_from_panel


def test_xui_client_from_panel() -> None:
    panel = Panel(
        id=2,
        name="EU",
        base_url="https://eu.example.com:2053",
        api_token="tok",
        username=None,
        password=None,
        sub_public_url="https://sub.example/save/",
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=False,
        is_active=True,
    )
    client = xui_client_from_panel(panel)
    assert client.base_url == "https://eu.example.com:2053"
    assert client.api_token == "tok"
    assert client.auto_reseller_group is False


def test_get_client_missing() -> None:
    reg = PanelRegistry()
    with pytest.raises(PanelNotFoundError):
        reg.get_client(99)


def test_load_from_db_sync() -> None:
    import asyncio

    panel = Panel(
        id=1,
        name="Default",
        base_url="https://x.example.com",
        api_token="a",
        username=None,
        password=None,
        sub_public_url=None,
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=True,
    )
    session = AsyncMock()

    async def _run() -> None:
        with patch("services.panel_registry.PanelRepository") as Repo:
            Repo.return_value.list_active = AsyncMock(return_value=[panel])
            reg = PanelRegistry()
            await reg.load_from_db(session)
        assert reg.loaded_panel_ids() == [1]
        assert reg.get_client(1).base_url == "https://x.example.com"
        await reg.close_all()

    asyncio.run(_run())
