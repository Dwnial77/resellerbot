"""Tests for multi-panel reseller assignments (v1.2.0)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import Panel, Reseller, ResellerPanel
from db.repository import ResellerPanelRepository, ResellerRepository
from services.quota import QuotaExceeded, QuotaService
from services.reseller_panel_edit import (
    apply_panel_toggle_create_allowed,
    apply_set_default_panel,
)
from xui.client import gb_to_bytes


def _reseller(*, panel_id: int = 1, tg_id: int = 100) -> Reseller:
    return Reseller(
        telegram_id=tg_id,
        panel_id=panel_id,
        quota_bytes=gb_to_bytes(100),
        lifetime_allocated_bytes=0,
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def _assignment(
    reseller: Reseller,
    panel_id: int,
    *,
    quota_gb: float = 100,
    lifetime_gb: float = 0,
    is_active: bool = True,
) -> ResellerPanel:
    return ResellerPanel(
        reseller_tg_id=reseller.telegram_id,
        panel_id=panel_id,
        quota_bytes=gb_to_bytes(quota_gb),
        lifetime_allocated_bytes=gb_to_bytes(lifetime_gb),
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=is_active,
    )


def _quota_svc_mocks(
    reseller: Reseller,
    assignment: ResellerPanel,
    *,
    active_gb: float = 0,
    client_count: int = 0,
) -> QuotaService:
    reseller_repo = AsyncMock()
    reseller_repo.active_bytes_on_panel = AsyncMock(
        return_value=gb_to_bytes(active_gb)
    )
    reseller_repo.client_count_on_panel = AsyncMock(return_value=client_count)
    panel_repo = AsyncMock()
    panel_repo.get = AsyncMock(return_value=assignment)
    return QuotaService(reseller_repo, panel_repo)


def test_quota_status_per_panel() -> None:
    async def _run() -> None:
        reseller = _reseller()
        a1 = _assignment(reseller, 1, quota_gb=100, lifetime_gb=30)
        svc = _quota_svc_mocks(reseller, a1, active_gb=10, client_count=2)
        st = await svc.status(reseller, 1)
        assert st.panel_id == 1
        assert st.lifetime_gb == 30.0
        assert st.remaining_gb == 70.0
        assert st.client_count == 2

    asyncio.run(_run())


def test_validate_create_on_panel_b() -> None:
    async def _run() -> None:
        reseller = _reseller(panel_id=1)
        assignment_b = _assignment(reseller, 2, quota_gb=50, lifetime_gb=10)
        reseller_repo = AsyncMock()
        reseller_repo.active_bytes_on_panel = AsyncMock(return_value=0)
        reseller_repo.client_count_on_panel = AsyncMock(return_value=0)
        panel_repo = AsyncMock()
        panel_repo.get = AsyncMock(return_value=assignment_b)
        svc = QuotaService(reseller_repo, panel_repo)
        allocated = await svc.validate_create(reseller, 2, 20, [1])
        assert allocated == gb_to_bytes(20)

    asyncio.run(_run())


def test_validate_create_rejects_unassigned_panel() -> None:
    async def _run() -> None:
        reseller = _reseller()
        panel_repo = AsyncMock()
        panel_repo.get = AsyncMock(return_value=None)
        svc = QuotaService(AsyncMock(), panel_repo)
        with pytest.raises(QuotaExceeded, match="اختصاص"):
            await svc.validate_create(reseller, 9, 10, [1])

    asyncio.run(_run())


def test_apply_set_default_panel() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller(panel_id=1)
        assignment = _assignment(reseller, 2, quota_gb=200)
        panel = Panel(
            id=2,
            name="Panel B",
            base_url="https://x",
            api_token="t",
            verify_ssl=True,
            auto_vision_flow=True,
            auto_reseller_group=True,
            is_active=True,
        )

        with (
            patch(
                "services.reseller_panel_edit.ResellerRepository"
            ) as ResellerRepo,
            patch(
                "services.reseller_panel_edit.ResellerPanelRepository"
            ) as PanelAssignRepo,
            patch("services.reseller_panel_edit.PanelRepository") as PanelRepo,
        ):
            ResellerRepo.return_value.get = AsyncMock(return_value=reseller)
            PanelAssignRepo.return_value.get = AsyncMock(return_value=assignment)
            PanelRepo.return_value.get = AsyncMock(return_value=panel)

            result = await apply_set_default_panel(session, 100, 2)

        assert reseller.panel_id == 2
        assert result.panel.name == "Panel B"
        assert "Panel B" in result.message_text

    asyncio.run(_run())


def test_status_works_on_inactive_assignment() -> None:
    async def _run() -> None:
        reseller = _reseller()
        inactive = _assignment(reseller, 1, quota_gb=100, lifetime_gb=20, is_active=False)
        svc = _quota_svc_mocks(reseller, inactive, client_count=1)
        st = await svc.status(reseller, 1)
        assert st.remaining_gb == 80.0
        assert st.client_count == 1

    asyncio.run(_run())


def test_validate_create_rejects_inactive_assignment() -> None:
    async def _run() -> None:
        reseller = _reseller()
        inactive = _assignment(reseller, 1, is_active=False)
        svc = _quota_svc_mocks(reseller, inactive)
        with pytest.raises(QuotaExceeded, match="ممنوع"):
            await svc.validate_create(reseller, 1, 10, [1])

    asyncio.run(_run())


def test_validate_add_traffic_allows_inactive_assignment() -> None:
    async def _run() -> None:
        reseller = _reseller()
        inactive = _assignment(reseller, 1, quota_gb=100, lifetime_gb=10, is_active=False)
        svc = _quota_svc_mocks(reseller, inactive)
        allocated = await svc.validate_add_traffic(reseller, 1, 20)
        assert allocated == gb_to_bytes(20)

    asyncio.run(_run())


def test_apply_panel_toggle_create_allowed() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller()
        assignment = _assignment(reseller, 1, is_active=True)
        panel = Panel(
            id=1,
            name="Panel A",
            base_url="https://x",
            api_token="t",
            verify_ssl=True,
            auto_vision_flow=True,
            auto_reseller_group=True,
            is_active=True,
        )
        toggled = _assignment(reseller, 1, is_active=False)

        with (
            patch("services.reseller_panel_edit.ResellerRepository") as ResellerRepo,
            patch("services.reseller_panel_edit.ResellerPanelRepository") as PanelAssignRepo,
            patch("services.reseller_panel_edit.PanelRepository") as PanelRepo,
        ):
            ResellerRepo.return_value.get = AsyncMock(return_value=reseller)
            PanelAssignRepo.return_value.get = AsyncMock(return_value=assignment)
            PanelAssignRepo.return_value.set_active = AsyncMock(return_value=toggled)
            PanelRepo.return_value.get = AsyncMock(return_value=panel)

            result = await apply_panel_toggle_create_allowed(session, 100, 1)

        PanelAssignRepo.return_value.set_active.assert_awaited_once_with(100, 1, False)
        assert "ممنوع" in result.message_text

    asyncio.run(_run())


def test_migration_007_backfill(tmp_path) -> None:
    async def _run() -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from db.migrations import run_pending_migrations
        from db.models import Base

        db_path = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(run_pending_migrations)

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            reseller_repo = ResellerRepository(session)
            await reseller_repo.upsert(
                100,
                gb_to_bytes(50),
                panel_id=1,
                allowed_inbound_ids=[1],
            )
            await session.commit()
            rows = await ResellerPanelRepository(session).list_for_reseller(100)
            assert len(rows) == 1
            assert rows[0].panel_id == 1
            assert rows[0].quota_bytes == gb_to_bytes(50)

        await engine.dispose()

    asyncio.run(_run())
