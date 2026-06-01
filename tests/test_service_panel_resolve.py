import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import ClientRecord, Panel, Reseller
from services.panel_registry import PanelRegistry, xui_client_from_panel
from services.panel_resolve import (
    ServicePanelUnavailableError,
    list_accessible_panel_ids,
    xui_for_record,
)
from services.reseller_service import ResellerService
from xui.client import XuiClient, XuiError


def _panel(panel_id: int = 1) -> Panel:
    return Panel(
        id=panel_id,
        name="P",
        base_url="https://x.example.com",
        api_token="tok",
        username=None,
        password=None,
        sub_public_url=None,
        verify_ssl=True,
        auto_vision_flow=True,
        auto_reseller_group=True,
        is_active=True,
    )


def _record(*, panel_id: int = 1, email: str = "ali-client-abcd") -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=panel_id,
        email=email,
        sub_id="sub1",
        inbound_ids="[1]",
        allocated_bytes=1,
        expiry_time=0,
    )


def test_xui_for_record_success() -> None:
    panel = _panel(1)
    reg = PanelRegistry()
    reg._clients[1] = xui_client_from_panel(panel)
    xui = xui_for_record(reg, _record(panel_id=1))
    assert isinstance(xui, XuiClient)


def test_xui_for_record_unavailable() -> None:
    reg = PanelRegistry()
    with pytest.raises(ServicePanelUnavailableError) as exc:
        xui_for_record(reg, _record(panel_id=2))
    assert exc.value.panel_id == 2


def test_list_accessible_panel_ids() -> None:
    reg = PanelRegistry()
    reg._clients[1] = MagicMock(spec=XuiClient)
    reg._clients[3] = MagicMock(spec=XuiClient)
    assert list_accessible_panel_ids(reg) == {1, 3}


def test_get_owned_record_ignores_reseller_panel_id() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = Reseller(
            telegram_id=100,
            panel_id=2,
            quota_bytes=0,
            allowed_inbound_ids="[1]",
            attach_inbound_ids="[1]",
        )
        record = _record(panel_id=1)
        xui = MagicMock(spec=XuiClient)

        with patch("services.reseller_service.ResellerRepository") as RRepo:
            with patch("services.reseller_service.ClientRepository") as CRepo:
                RRepo.return_value = MagicMock()
                client_repo = CRepo.return_value
                client_repo.get_for_reseller_email = AsyncMock(return_value=record)
                client_repo.session = session
                svc = ResellerService(session, xui)
                got = await svc._get_owned_record(reseller, record.email)
        assert got.panel_id == 1
        client_repo.get_for_reseller_email.assert_awaited_once_with(
            100, record.email
        )

    asyncio.run(_run())


def test_reseller_service_rejects_none_xui() -> None:
    with pytest.raises(XuiError, match="پنل اختصاصی"):
        ResellerService(AsyncMock(), None)
