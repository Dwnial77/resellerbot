"""Tests for adding traffic to existing client services."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from db.models import ClientRecord, Reseller, ResellerPanel
from services.quota import QuotaExceeded, QuotaService
from services.reseller_service import AddTrafficResult, ResellerService
from xui.client import XuiError, gb_to_bytes


def _reseller(
    *,
    quota_gb: float = 500,
    lifetime_gb: float = 0,
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


def _quota_svc(reseller: Reseller, *, quota_gb: float, lifetime_gb: float) -> QuotaService:
    assignment = _assignment(reseller, quota_gb=quota_gb, lifetime_gb=lifetime_gb)
    repo = AsyncMock()
    repo.active_bytes = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count = AsyncMock(return_value=1)
    repo.active_bytes_on_panel = AsyncMock(return_value=gb_to_bytes(50))
    repo.client_count_on_panel = AsyncMock(return_value=1)
    panel_repo = AsyncMock()
    panel_repo.get = AsyncMock(return_value=assignment)
    return QuotaService(repo, panel_repo)


def _record(*, allocated_gb: float = 10) -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=1,
        email="ali-client-test",
        inbound_ids="[1]",
        allocated_bytes=gb_to_bytes(allocated_gb),
        expiry_time=0,
    )


def test_validate_add_traffic_success() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=400)
        svc = _quota_svc(reseller, quota_gb=500, lifetime_gb=400)
        allocated = await svc.validate_add_traffic(reseller, 1, 50)
        assert allocated == gb_to_bytes(50)

    asyncio.run(_run())


def test_validate_add_traffic_rejects_over_remaining() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=500)
        svc = _quota_svc(reseller, quota_gb=500, lifetime_gb=500)
        with pytest.raises(QuotaExceeded, match="باقی"):
            await svc.validate_add_traffic(reseller, 1, 10)

    asyncio.run(_run())


def test_validate_add_traffic_rejects_zero_volume() -> None:
    async def _run() -> None:
        reseller = _reseller()
        assignment = _assignment(reseller, quota_gb=500, lifetime_gb=0)
        repo = AsyncMock()
        panel_repo = AsyncMock()
        panel_repo.get = AsyncMock(return_value=assignment)
        svc = QuotaService(repo, panel_repo)
        with pytest.raises(QuotaExceeded, match="بزرگ"):
            await svc.validate_add_traffic(reseller, 1, 0)

    asyncio.run(_run())


def test_validate_add_traffic_rejects_inactive() -> None:
    async def _run() -> None:
        reseller = _reseller()
        reseller.is_active = False
        repo = AsyncMock()
        panel_repo = AsyncMock()
        svc = QuotaService(repo, panel_repo)
        with pytest.raises(QuotaExceeded, match="غیرفعال"):
            await svc.validate_add_traffic(reseller, 1, 10)

    asyncio.run(_run())


def test_add_service_traffic_updates_panel_and_db() -> None:
    async def _run() -> None:
        session = AsyncMock()
        xui = AsyncMock()
        xui.add_client_traffic_bytes = AsyncMock(return_value={})

        reseller = _reseller(quota_gb=500, lifetime_gb=100)
        record = _record(allocated_gb=10)

        reseller_repo = AsyncMock()
        panel_repo = AsyncMock()
        client_repo = AsyncMock()
        client_repo.get_for_reseller_email = AsyncMock(return_value=record)
        updated = _record(allocated_gb=20)
        updated.allocated_bytes = gb_to_bytes(20)
        client_repo.add_allocated_bytes = AsyncMock(return_value=updated)
        reseller_repo.get = AsyncMock(return_value=reseller)
        reseller_repo.add_lifetime_allocated = AsyncMock()
        panel_repo.add_lifetime_allocated = AsyncMock()

        svc = ResellerService(session, xui)
        svc.reseller_repo = reseller_repo
        svc.panel_repo = panel_repo
        svc.client_repo = client_repo
        svc.quota = _quota_svc(reseller, quota_gb=500, lifetime_gb=100)

        result = await svc.add_service_traffic(reseller, record.email, 10)

        assert isinstance(result, AddTrafficResult)
        assert result.added_bytes == gb_to_bytes(10)
        assert result.new_total_bytes == gb_to_bytes(20)
        xui.add_client_traffic_bytes.assert_awaited_once_with(
            record.email, gb_to_bytes(10)
        )
        client_repo.add_allocated_bytes.assert_awaited_once()
        panel_repo.add_lifetime_allocated.assert_not_called()
        reseller_repo.add_lifetime_allocated.assert_awaited_once_with(
            reseller.telegram_id, gb_to_bytes(10)
        )

    asyncio.run(_run())


def test_add_service_traffic_rejects_insufficient_quota() -> None:
    async def _run() -> None:
        session = AsyncMock()
        xui = AsyncMock()
        reseller = _reseller(quota_gb=500, lifetime_gb=500)
        record = _record()

        reseller_repo = AsyncMock()
        panel_repo = AsyncMock()
        client_repo = AsyncMock()
        client_repo.get_for_reseller_email = AsyncMock(return_value=record)

        svc = ResellerService(session, xui)
        svc.reseller_repo = reseller_repo
        svc.panel_repo = panel_repo
        svc.client_repo = client_repo
        svc.quota = _quota_svc(reseller, quota_gb=500, lifetime_gb=500)

        with pytest.raises(XuiError, match="باقی"):
            await svc.add_service_traffic(reseller, record.email, 10)

        xui.add_client_traffic_bytes.assert_not_called()

    asyncio.run(_run())
