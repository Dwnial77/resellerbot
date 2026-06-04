"""Tests for lifetime quota consumption (anti-abuse on service delete)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import ClientRecord, Reseller
from services.quota import QuotaExceeded, QuotaService
from services.reseller_edit import apply_add_quota, apply_reset_quota_usage
from services.reseller_service import (
    DeleteServiceResult,
    ResellerService,
    is_quota_refund_eligible,
)
from bot.utils.format_traffic import client_traffic_used_bytes
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


def test_status_uses_lifetime_for_remaining() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=300)
        repo = AsyncMock()
        repo.active_bytes = AsyncMock(return_value=gb_to_bytes(100))
        repo.client_count = AsyncMock(return_value=2)

        st = await QuotaService(repo).status(reseller)
        assert st.active_gb == 100.0
        assert st.lifetime_gb == 300.0
        assert st.remaining_gb == 200.0
        assert st.used_bytes == st.lifetime_bytes

    asyncio.run(_run())


def test_validate_create_rejects_over_remaining() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=500)
        repo = AsyncMock()
        repo.active_bytes = AsyncMock(return_value=0)
        repo.client_count = AsyncMock(return_value=0)

        with pytest.raises(QuotaExceeded, match="باقی"):
            await QuotaService(repo).validate_create(reseller, 10, [1])

    asyncio.run(_run())


def test_validate_create_allows_within_remaining() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=400)
        repo = AsyncMock()
        repo.active_bytes = AsyncMock(return_value=gb_to_bytes(50))
        repo.client_count = AsyncMock(return_value=1)

        allocated = await QuotaService(repo).validate_create(reseller, 50, [1])
        assert allocated == gb_to_bytes(50)

    asyncio.run(_run())


def test_apply_add_quota_increases_ceiling() -> None:
    async def _run() -> None:
        session = AsyncMock()
        row = _reseller(quota_gb=500, lifetime_gb=500)
        repo = MagicMock()
        repo.get = AsyncMock(return_value=row)
        repo.add_quota_bytes = AsyncMock(
            return_value=Reseller(
                telegram_id=100,
                panel_id=1,
                quota_bytes=gb_to_bytes(1000),
                lifetime_allocated_bytes=gb_to_bytes(500),
                allowed_inbound_ids="[1]",
                attach_inbound_ids="[1]",
            )
        )

        with patch("services.reseller_edit.ResellerRepository", return_value=repo):
            result = await apply_add_quota(session, 100, 500)

        repo.add_quota_bytes.assert_awaited_once()
        assert "500" in result.message_text

    asyncio.run(_run())


def test_apply_reset_quota_usage_syncs_lifetime_to_active() -> None:
    async def _run() -> None:
        session = AsyncMock()
        active = gb_to_bytes(80)
        row = _reseller(quota_gb=500, lifetime_gb=500)
        reset_row = _reseller(quota_gb=500, lifetime_gb=80)
        reset_row.lifetime_allocated_bytes = active

        repo = MagicMock()
        repo.get = AsyncMock(return_value=row)
        repo.reset_lifetime_to_active = AsyncMock(return_value=reset_row)
        repo.active_bytes = AsyncMock(return_value=active)
        repo.client_count = AsyncMock(return_value=2)

        with patch("services.reseller_edit.ResellerRepository", return_value=repo):
            result = await apply_reset_quota_usage(session, 100)

        repo.reset_lifetime_to_active.assert_awaited_once_with(100)
        assert "ریست" in result.message_text

    asyncio.run(_run())


def test_client_traffic_used_bytes_sums_up_down() -> None:
    assert client_traffic_used_bytes({"up": 100, "down": 200}) == 300
    assert client_traffic_used_bytes([{"up": 50, "down": 0}]) == 50


def test_is_quota_refund_eligible_threshold() -> None:
    one_gb = gb_to_bytes(1)
    assert is_quota_refund_eligible(0, max_traffic_gb=1.0) is True
    assert is_quota_refund_eligible(one_gb - 1, max_traffic_gb=1.0) is True
    assert is_quota_refund_eligible(one_gb, max_traffic_gb=1.0) is False
    assert is_quota_refund_eligible(one_gb + 1, max_traffic_gb=1.0) is False


def _client_record(*, allocated_gb: float = 50) -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=1,
        email="r100_test",
        inbound_ids="[1]",
        allocated_bytes=gb_to_bytes(allocated_gb),
        expiry_time=0,
    )


def _delete_service_mocks(
    *,
    used_bytes: int,
    allocated_gb: float = 50,
    traffic_error: bool = False,
) -> tuple[ResellerService, AsyncMock, AsyncMock, AsyncMock]:
    session = AsyncMock()
    xui = AsyncMock()
    if traffic_error:
        xui.get_traffic = AsyncMock(side_effect=XuiError("panel down"))
    else:
        xui.get_traffic = AsyncMock(return_value={"up": used_bytes, "down": 0})
    xui.delete_client = AsyncMock(return_value={})

    reseller_repo = AsyncMock()
    reseller_repo.subtract_lifetime_allocated = AsyncMock()

    client_repo = AsyncMock()
    record = _client_record(allocated_gb=allocated_gb)
    client_repo.get_for_reseller_email = AsyncMock(return_value=record)
    client_repo.delete = AsyncMock()
    client_repo.session = session

    svc = ResellerService(session, xui)
    svc.reseller_repo = reseller_repo
    svc.client_repo = client_repo
    return svc, xui, reseller_repo, client_repo


async def _delete_service(
    svc: ResellerService, reseller: Reseller, email: str = "r100_test"
) -> DeleteServiceResult:
    with patch(
        "services.reseller_service.UsageAlertRepository.clear",
        new_callable=AsyncMock,
    ):
        return await svc.delete_service(reseller, email)


def test_delete_service_refunds_when_used_under_1gb() -> None:
    async def _run() -> None:
        svc, _, reseller_repo, _ = _delete_service_mocks(used_bytes=500 * 1024**2)
        result = await _delete_service(svc, _reseller())
        assert isinstance(result, DeleteServiceResult)
        assert result.refunded_bytes == gb_to_bytes(50)
        reseller_repo.subtract_lifetime_allocated.assert_awaited_once_with(
            100, gb_to_bytes(50)
        )

    asyncio.run(_run())


def test_delete_service_no_refund_at_1gb() -> None:
    async def _run() -> None:
        svc, _, reseller_repo, _ = _delete_service_mocks(used_bytes=gb_to_bytes(1))
        result = await _delete_service(svc, _reseller())
        assert result.refunded_bytes == 0
        reseller_repo.subtract_lifetime_allocated.assert_not_called()

    asyncio.run(_run())


def test_delete_service_no_refund_on_traffic_error() -> None:
    async def _run() -> None:
        svc, _, reseller_repo, client_repo = _delete_service_mocks(
            used_bytes=0, traffic_error=True
        )
        result = await _delete_service(svc, _reseller())
        assert result.refunded_bytes == 0
        reseller_repo.subtract_lifetime_allocated.assert_not_called()
        client_repo.delete.assert_awaited_once()

    asyncio.run(_run())
