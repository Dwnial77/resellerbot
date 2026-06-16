"""Tests for reducing traffic on existing client services."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from db.models import ClientRecord, Reseller, ResellerPanel
from services.quota import QuotaExceeded, QuotaService
from services.reseller_service import RemoveTrafficResult, ResellerService
from xui.client import XuiError, gb_to_bytes


def _reseller(
    *,
    quota_gb: float = 500,
    lifetime_gb: float = 100,
) -> Reseller:
    return Reseller(
        telegram_id=100,
        panel_id=1,
        quota_bytes=gb_to_bytes(quota_gb),
        lifetime_allocated_bytes=gb_to_bytes(lifetime_gb),
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def _assignment(reseller: Reseller, *, quota_gb: float, lifetime_gb: float) -> ResellerPanel:
    return ResellerPanel(
        reseller_tg_id=reseller.telegram_id,
        panel_id=1,
        quota_bytes=gb_to_bytes(quota_gb),
        lifetime_allocated_bytes=gb_to_bytes(lifetime_gb),
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def _quota_svc(reseller: Reseller) -> QuotaService:
    assignment = _assignment(reseller, quota_gb=500, lifetime_gb=100)
    repo = AsyncMock()
    repo.active_bytes = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count = AsyncMock(return_value=1)
    repo.active_bytes_on_panel = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count_on_panel = AsyncMock(return_value=1)
    panel_repo = AsyncMock()
    panel_repo.get = AsyncMock(return_value=assignment)
    return QuotaService(repo, panel_repo)


def _record(*, allocated_gb: float = 50) -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=1,
        email="ali-client-test",
        inbound_ids="[1]",
        allocated_bytes=gb_to_bytes(allocated_gb),
        expiry_time=0,
    )


def test_validate_remove_traffic_success() -> None:
    reseller = _reseller()
    svc = _quota_svc(reseller)
    removed = svc.validate_remove_traffic(
        reseller,
        10,
        current_allocated_bytes=gb_to_bytes(50),
        used_bytes=gb_to_bytes(12),
    )
    assert removed == gb_to_bytes(10)


def test_validate_remove_traffic_rejects_over_current_cap() -> None:
    reseller = _reseller()
    svc = _quota_svc(reseller)
    with pytest.raises(QuotaExceeded, match="سقف فعلی"):
        svc.validate_remove_traffic(
            reseller,
            60,
            current_allocated_bytes=gb_to_bytes(50),
            used_bytes=0,
        )


def test_validate_remove_traffic_rejects_below_used() -> None:
    reseller = _reseller()
    svc = _quota_svc(reseller)
    with pytest.raises(QuotaExceeded, match="مصرف فعلی"):
        svc.validate_remove_traffic(
            reseller,
            45,
            current_allocated_bytes=gb_to_bytes(50),
            used_bytes=gb_to_bytes(12),
        )


def test_validate_remove_traffic_rejects_inactive() -> None:
    reseller = _reseller()
    reseller.is_active = False
    svc = _quota_svc(reseller)
    with pytest.raises(QuotaExceeded, match="غیرفعال"):
        svc.validate_remove_traffic(
            reseller,
            10,
            current_allocated_bytes=gb_to_bytes(50),
            used_bytes=0,
        )


def test_remove_service_traffic_updates_panel_and_db() -> None:
    async def _run() -> None:
        session = AsyncMock()
        xui = AsyncMock()
        xui.get_traffic = AsyncMock(return_value={"up": 0, "down": gb_to_bytes(12)})
        xui.subtract_client_traffic_bytes = AsyncMock(return_value={})

        reseller = _reseller(quota_gb=500, lifetime_gb=100)
        record = _record(allocated_gb=50)

        reseller_repo = AsyncMock()
        panel_repo = AsyncMock()
        client_repo = AsyncMock()
        client_repo.get_for_reseller_email = AsyncMock(return_value=record)
        updated = _record(allocated_gb=40)
        updated.allocated_bytes = gb_to_bytes(40)
        client_repo.subtract_allocated_bytes = AsyncMock(return_value=updated)
        reseller_repo.subtract_lifetime_allocated = AsyncMock()
        panel_repo.subtract_lifetime_allocated = AsyncMock()

        svc = ResellerService(session, xui)
        svc.reseller_repo = reseller_repo
        svc.panel_repo = panel_repo
        svc.client_repo = client_repo
        svc.quota = _quota_svc(reseller)

        result = await svc.remove_service_traffic(reseller, record.email, 10)

        assert isinstance(result, RemoveTrafficResult)
        assert result.removed_bytes == gb_to_bytes(10)
        assert result.new_total_bytes == gb_to_bytes(40)
        xui.subtract_client_traffic_bytes.assert_awaited_once_with(
            record.email, gb_to_bytes(10)
        )
        client_repo.subtract_allocated_bytes.assert_awaited_once()
        panel_repo.subtract_lifetime_allocated.assert_not_called()
        reseller_repo.subtract_lifetime_allocated.assert_awaited_once_with(
            reseller.telegram_id, gb_to_bytes(10)
        )

    asyncio.run(_run())


def test_remove_service_traffic_rejects_below_used() -> None:
    async def _run() -> None:
        session = AsyncMock()
        xui = AsyncMock()
        xui.get_traffic = AsyncMock(return_value={"up": 0, "down": gb_to_bytes(40)})

        reseller = _reseller()
        record = _record(allocated_gb=50)

        client_repo = AsyncMock()
        client_repo.get_for_reseller_email = AsyncMock(return_value=record)

        svc = ResellerService(session, xui)
        svc.client_repo = client_repo
        svc.quota = _quota_svc(reseller)

        with pytest.raises(XuiError, match="مصرف فعلی"):
            await svc.remove_service_traffic(reseller, record.email, 15)

        xui.subtract_client_traffic_bytes.assert_not_called()

    asyncio.run(_run())
