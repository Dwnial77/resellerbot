"""XuiClient._request retry policy and error normalization."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from db.models import Reseller, ResellerPanel
from services.reseller_service import ResellerService
from xui.client import XuiApiError, XuiClient, XuiError, gb_to_bytes


def _client_with(side_effect) -> tuple[XuiClient, AsyncMock]:
    xui = XuiClient("http://panel.example", api_token="t", max_retries=3)
    http = MagicMock()
    http.request = AsyncMock(side_effect=side_effect)
    xui._client = http
    return xui, http.request


def test_non_idempotent_post_is_not_retried(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    xui, request = _client_with(httpx.ReadTimeout("lost"))
    with pytest.raises(XuiError):
        asyncio.run(xui.add_client_traffic_bytes("a", 10))
    assert request.await_count == 1


def test_idempotent_get_is_retried_and_wrapped(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    xui, request = _client_with(httpx.ConnectError("down"))
    with pytest.raises(XuiError) as exc:
        asyncio.run(xui.list_inbounds())
    assert not isinstance(exc.value, httpx.HTTPError)
    assert request.await_count == 3


def test_panel_api_error_is_not_retried(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    resp = httpx.Response(
        200, json={"success": False, "msg": "nope"},
        request=httpx.Request("GET", "http://panel.example"),
    )
    xui, request = _client_with([resp, resp, resp])
    with pytest.raises(XuiApiError):
        asyncio.run(xui.list_inbounds())
    assert request.await_count == 1


def _reseller() -> Reseller:
    return Reseller(
        telegram_id=100, panel_id=1, display_name="ali",
        quota_bytes=gb_to_bytes(500), lifetime_allocated_bytes=0,
        allowed_inbound_ids="[1]", attach_inbound_ids="[1]", is_active=True,
    )


def _create_svc(xui: AsyncMock) -> ResellerService:
    svc = ResellerService(AsyncMock(), xui)
    svc.panel_repo = AsyncMock()
    svc.panel_repo.get = AsyncMock(
        return_value=ResellerPanel(
            reseller_tg_id=100, panel_id=1, quota_bytes=0,
            allowed_inbound_ids="[1]", attach_inbound_ids="[1]", is_active=True,
        )
    )
    svc.quota = AsyncMock()
    svc.quota.validate_create = AsyncMock(return_value=gb_to_bytes(20))
    svc.client_repo = AsyncMock()
    svc.client_repo.email_exists = AsyncMock(return_value=False)
    svc.client_repo.get_for_reseller_email = AsyncMock(return_value=None)
    svc.reseller_repo = AsyncMock()
    return svc


def test_create_removes_panel_client_when_delivery_fails() -> None:
    async def _run() -> None:
        xui = AsyncMock()
        xui.auto_reseller_group = False
        xui.get_client = AsyncMock(return_value=None)
        xui.create_client = AsyncMock(return_value=({}, "sub"))
        xui.get_client_delivery = AsyncMock(side_effect=XuiError("links failed"))
        svc = _create_svc(xui)
        with pytest.raises(XuiError):
            await svc.create_service(
                _reseller(), 20, client_suffix="x1", panel_id=1
            )
        xui.delete_client.assert_awaited_once_with("ali-client-x1")
        svc.client_repo.delete.assert_awaited_once()
        svc.reseller_repo.add_lifetime_allocated.assert_not_called()

    asyncio.run(_run())


def test_create_keeps_panel_untouched_on_definitive_panel_error() -> None:
    async def _run() -> None:
        xui = AsyncMock()
        xui.auto_reseller_group = False
        xui.get_client = AsyncMock(return_value=None)
        xui.create_client = AsyncMock(side_effect=XuiApiError("inbound missing"))
        svc = _create_svc(xui)
        with pytest.raises(XuiError):
            await svc.create_service(
                _reseller(), 20, client_suffix="x1", panel_id=1
            )
        xui.delete_client.assert_not_called()

    asyncio.run(_run())


def test_create_rejects_name_used_on_another_panel() -> None:
    async def _run() -> None:
        xui = AsyncMock()
        svc = _create_svc(xui)
        svc.client_repo.get_for_reseller_email = AsyncMock(return_value=object())
        with pytest.raises(XuiError, match="قبلاً"):
            await svc.create_service(
                _reseller(), 20, client_suffix="x1", panel_id=1
            )
        xui.create_client.assert_not_called()

    asyncio.run(_run())
