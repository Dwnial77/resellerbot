"""Tests for manual create flow and minimum client volume."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from bot.keyboards.common import template_picker_kb
from db.models import Reseller, ResellerPanel, ServiceTemplate
from services.client_volume import (
    MIN_CLIENT_VOLUME_GB,
    ClientVolumeTooLowError,
    validate_client_volume_gb,
)
from services.quota import QuotaExceeded, QuotaService
from xui.client import gb_to_bytes


def _reseller(*, quota_gb: float = 500, lifetime_gb: float = 0) -> Reseller:
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


def _quota_service(reseller: Reseller, *, quota_gb: float, lifetime_gb: float) -> QuotaService:
    assignment = _assignment(reseller, quota_gb=quota_gb, lifetime_gb=lifetime_gb)
    repo = AsyncMock()
    repo.active_bytes_on_panel = AsyncMock(return_value=0)
    repo.client_count_on_panel = AsyncMock(return_value=0)
    panel_repo = AsyncMock()
    panel_repo.get = AsyncMock(return_value=assignment)
    return QuotaService(repo, panel_repo)


def test_validate_client_volume_gb_accepts_minimum() -> None:
    validate_client_volume_gb(MIN_CLIENT_VOLUME_GB)


def test_validate_client_volume_gb_rejects_below_minimum() -> None:
    with pytest.raises(ClientVolumeTooLowError):
        validate_client_volume_gb(19)


def test_validate_create_rejects_below_minimum() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=0)
        svc = _quota_service(reseller, quota_gb=500, lifetime_gb=0)
        with pytest.raises(QuotaExceeded, match="حداقل"):
            await svc.validate_create(reseller, 1, 19, [1])

    asyncio.run(_run())


def test_validate_create_accepts_minimum_volume() -> None:
    async def _run() -> None:
        reseller = _reseller(quota_gb=500, lifetime_gb=0)
        svc = _quota_service(reseller, quota_gb=500, lifetime_gb=0)
        allocated = await svc.validate_create(reseller, 1, 20, [1])
        assert allocated == gb_to_bytes(20)

    asyncio.run(_run())


def test_template_picker_kb_filters_below_minimum() -> None:
    templates = [
        ServiceTemplate(
            id=1,
            name="10GB/30d",
            volume_gb=10.0,
            expiry_days=30,
            sort_order=1,
            is_active=True,
        ),
        ServiceTemplate(
            id=2,
            name="50GB/90d",
            volume_gb=50.0,
            expiry_days=90,
            sort_order=2,
            is_active=True,
        ),
    ]
    kb = template_picker_kb(templates)
    template_rows = [
        row[0].callback_data
        for row in kb.inline_keyboard
        if row[0].callback_data.startswith("tpl:")
    ]
    assert template_rows == ["tpl:2"]
    assert kb.inline_keyboard[-2][0].callback_data == "create:manual"
