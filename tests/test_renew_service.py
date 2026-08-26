"""Tests for renewing (redefining) an existing client service."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import ClientRecord, Reseller, ResellerPanel
from services.quota import QuotaExceeded, QuotaService
from services.reseller_service import RenewServiceResult, ResellerService
from xui.client import XuiError, gb_to_bytes


def _reseller(*, quota_gb: float = 500, lifetime_gb: float = 100) -> Reseller:
    return Reseller(
        telegram_id=100,
        panel_id=1,
        quota_bytes=gb_to_bytes(quota_gb),
        lifetime_allocated_bytes=gb_to_bytes(lifetime_gb),
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def _assignment(*, max_clients: int | None = None) -> ResellerPanel:
    return ResellerPanel(
        reseller_tg_id=100,
        panel_id=1,
        quota_bytes=gb_to_bytes(500),
        lifetime_allocated_bytes=0,
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        max_clients=max_clients,
        is_active=True,
    )


def _quota_svc(
    reseller: Reseller,
    *,
    client_count: int = 5,
    assignment: ResellerPanel | None = None,
) -> QuotaService:
    repo = AsyncMock()
    repo.active_bytes = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count = AsyncMock(return_value=client_count)
    repo.active_bytes_on_panel = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count_on_panel = AsyncMock(return_value=client_count)
    panel_repo = AsyncMock()
    panel_repo.get = AsyncMock(return_value=assignment or _assignment())
    return QuotaService(repo, panel_repo)


def _record(*, allocated_gb: float = 30) -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=1,
        email="ali-client-test",
        inbound_ids="[1]",
        allocated_bytes=gb_to_bytes(allocated_gb),
        expiry_time=0,
    )


def _svc(
    reseller: Reseller,
    *,
    quota: QuotaService | None = None,
    new_allocated_gb: float = 50,
) -> tuple[ResellerService, AsyncMock, AsyncMock, AsyncMock]:
    session = AsyncMock()
    xui = AsyncMock()
    record = _record()

    reseller_repo = AsyncMock()
    reseller_repo.add_lifetime_allocated = AsyncMock()
    client_repo = AsyncMock()
    client_repo.session = session
    client_repo.get_for_reseller_email = AsyncMock(return_value=record)
    updated = _record(allocated_gb=new_allocated_gb)
    client_repo.set_allocated_bytes = AsyncMock(return_value=updated)
    client_repo.set_expiry_time = AsyncMock(return_value=updated)

    svc = ResellerService(session, xui)
    svc.reseller_repo = reseller_repo
    svc.client_repo = client_repo
    svc.quota = quota or _quota_svc(reseller)
    return svc, xui, reseller_repo, client_repo


async def _renew(
    svc: ResellerService, reseller: Reseller, volume_gb: float, days: int
) -> RenewServiceResult:
    with patch(
        "services.reseller_service.UsageAlertRepository.clear",
        new_callable=AsyncMock,
    ):
        return await svc.renew_service(reseller, "ali-client-test", volume_gb, days)


# --- validate_renew ---------------------------------------------------------


def test_validate_renew_success() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=400)
        allocated = await _quota_svc(reseller).validate_renew(reseller, 1, 50)
        assert allocated == gb_to_bytes(50)

    asyncio.run(_run())


def test_validate_renew_rejects_over_remaining() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=490)
        with pytest.raises(QuotaExceeded, match="باقی"):
            await _quota_svc(reseller).validate_renew(reseller, 1, 50)

    asyncio.run(_run())


def test_validate_renew_rejects_below_min_volume() -> None:
    async def _run() -> None:
        reseller = _reseller()
        with pytest.raises(QuotaExceeded, match="حداقل"):
            await _quota_svc(reseller).validate_renew(reseller, 1, 5)

    asyncio.run(_run())


def test_validate_renew_ignores_max_clients() -> None:
    """The client already exists, so the per-panel client cap must not apply."""

    async def _run() -> None:
        reseller = _reseller()
        quota = _quota_svc(
            reseller, client_count=10, assignment=_assignment(max_clients=10)
        )
        assert await quota.validate_renew(reseller, 1, 50) == gb_to_bytes(50)

    asyncio.run(_run())


def test_validate_renew_rejects_inactive_reseller() -> None:
    async def _run() -> None:
        reseller = _reseller()
        reseller.is_active = False
        with pytest.raises(QuotaExceeded, match="غیرفعال"):
            await _quota_svc(reseller).validate_renew(reseller, 1, 50)

    asyncio.run(_run())


# --- renew_service ----------------------------------------------------------


def test_renew_service_charges_quota_and_resets_traffic() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=100)
        svc, xui, reseller_repo, client_repo = _svc(reseller)

        result = await _renew(svc, reseller, 50, 30)

        assert isinstance(result, RenewServiceResult)
        assert result.charged_bytes == gb_to_bytes(50)
        assert result.new_total_bytes == gb_to_bytes(50)
        assert result.traffic_reset_failed is False
        assert result.new_expiry_ms > 0

        kwargs = xui.update_client_fields.await_args.kwargs
        assert kwargs["total_bytes"] == gb_to_bytes(50)
        assert kwargs["enable"] is True
        assert kwargs["expiry_ms"] > 0

        xui.reset_client_traffic.assert_awaited_once_with("ali-client-test")
        client_repo.set_allocated_bytes.assert_awaited_once()
        reseller_repo.add_lifetime_allocated.assert_awaited_once_with(
            100, gb_to_bytes(50)
        )

    asyncio.run(_run())


def test_renew_service_unlimited_expiry_sets_zero() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, _, _ = _svc(reseller)

        result = await _renew(svc, reseller, 50, 0)

        assert result.new_expiry_ms == 0
        assert xui.update_client_fields.await_args.kwargs["expiry_ms"] == 0

    asyncio.run(_run())


def test_renew_service_panel_failure_charges_nothing() -> None:
    """If the panel rejects the update, no quota is spent and nothing is reset."""

    async def _run() -> None:
        reseller = _reseller()
        svc, xui, reseller_repo, client_repo = _svc(reseller)
        xui.update_client_fields = AsyncMock(side_effect=XuiError("panel down"))

        with pytest.raises(XuiError, match="panel down"):
            await _renew(svc, reseller, 50, 30)

        xui.reset_client_traffic.assert_not_called()
        reseller_repo.add_lifetime_allocated.assert_not_called()
        client_repo.set_allocated_bytes.assert_not_called()

    asyncio.run(_run())


def test_renew_service_reports_failed_reset_but_still_charges() -> None:
    """A failed reset must not hand out free traffic — the charge still lands."""

    async def _run() -> None:
        reseller = _reseller()
        svc, xui, reseller_repo, _ = _svc(reseller)
        xui.reset_client_traffic = AsyncMock(side_effect=XuiError("reset failed"))

        result = await _renew(svc, reseller, 50, 30)

        assert result.traffic_reset_failed is True
        reseller_repo.add_lifetime_allocated.assert_awaited_once_with(
            100, gb_to_bytes(50)
        )

    asyncio.run(_run())


def test_renew_service_rejects_over_quota() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=490)
        svc, xui, reseller_repo, _ = _svc(reseller)

        with pytest.raises(XuiError, match="باقی"):
            await _renew(svc, reseller, 50, 30)

        xui.update_client_fields.assert_not_called()
        xui.reset_client_traffic.assert_not_called()
        reseller_repo.add_lifetime_allocated.assert_not_called()

    asyncio.run(_run())
