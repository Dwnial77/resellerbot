"""Provisioning for guest self-service purchases via a hidden system reseller."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClientRecord, GuestOrder, GuestSalesConfig, Plan, Reseller
from db.repository import ResellerRepository, inbound_ids_from_json
from services.panel_registry import PanelRegistry
from services.panel_resolve import (
    ServicePanelUnavailableError,
    xui_for_record,
    xui_for_reseller_panel,
)
from services.reseller_service import RenewServiceResult, ResellerService
from xui.client import ClientDelivery, XuiError, gb_to_bytes

SYSTEM_RESELLER_TG_ID = 0
SYSTEM_RESELLER_DISPLAY_NAME = "guest-sales"


async def ensure_system_reseller(
    session: AsyncSession, panel_id: int, inbound_ids: list[int]
) -> Reseller:
    repo = ResellerRepository(session)
    existing = await repo.get(SYSTEM_RESELLER_TG_ID)
    if existing is not None and existing.panel_id != panel_id:
        # upsert() keeps panel_id for existing rows; follow the guest-sales panel
        # so the assignment for the new panel is created below.
        existing.panel_id = panel_id
    row = await repo.upsert(
        SYSTEM_RESELLER_TG_ID,
        existing.quota_bytes if existing else 0,
        inbound_ids,
        panel_id=panel_id,
        attach_inbound_ids=inbound_ids,
        display_name=SYSTEM_RESELLER_DISPLAY_NAME,
        is_active=True,
    )
    if not row.is_system:
        row.is_system = True
        await session.commit()
        await session.refresh(row)
    return row


def order_terms(order: GuestOrder, plan: Plan | None) -> tuple[float, int] | None:
    """(volume_gb, expiry_days) the guest paid for: order snapshot, else plan."""
    if order.volume_gb is not None and order.expiry_days is not None:
        return float(order.volume_gb), int(order.expiry_days)
    if plan is None:
        return None
    return float(plan.volume_gb), int(plan.expiry_days)


async def deliver_guest_order(
    session: AsyncSession,
    panel_registry: PanelRegistry,
    order: GuestOrder,
    plan: Plan | None,
    guest_config: GuestSalesConfig,
) -> tuple[ClientRecord, ClientDelivery]:
    assert guest_config.panel_id is not None
    terms = order_terms(order, plan)
    if terms is None:
        raise XuiError("پلن این سفارش دیگر موجود نیست.")
    volume_gb, expiry_days = terms
    inbound_ids = inbound_ids_from_json(guest_config.inbound_ids)
    reseller = await ensure_system_reseller(
        session, guest_config.panel_id, inbound_ids
    )
    reseller_repo = ResellerRepository(session)
    plan_bytes = gb_to_bytes(volume_gb)
    await reseller_repo.add_quota_bytes(SYSTEM_RESELLER_TG_ID, plan_bytes)
    reseller = await reseller_repo.get(SYSTEM_RESELLER_TG_ID) or reseller

    try:
        xui = await xui_for_reseller_panel(
            panel_registry, session, reseller, guest_config.panel_id
        )
        svc = ResellerService(session, xui)
        return await svc.create_service(
            reseller,
            volume_gb=volume_gb,
            expiry_days=expiry_days,
            client_suffix=f"guest{order.telegram_id}_{order.id}",
            panel_id=guest_config.panel_id,
            inbound_ids=inbound_ids,
        )
    except Exception:
        # Nothing was delivered: take back the quota granted for this order.
        await reseller_repo.add_quota_bytes(SYSTEM_RESELLER_TG_ID, -plan_bytes)
        raise


async def renew_guest_order(
    session: AsyncSession,
    panel_registry: PanelRegistry,
    order: GuestOrder,
    plan: Plan | None,
) -> tuple[ClientRecord, RenewServiceResult]:
    """Renew the guest's existing account (full reset) on its own panel."""
    terms = order_terms(order, plan)
    if terms is None:
        raise XuiError("پلن این سفارش دیگر موجود نیست.")
    volume_gb, expiry_days = terms
    record = (
        await session.get(ClientRecord, order.target_client_record_id)
        if order.target_client_record_id is not None
        else None
    )
    if record is None or record.reseller_tg_id != SYSTEM_RESELLER_TG_ID:
        raise XuiError("اکانت موردنظر برای تمدید یافت نشد.")
    reseller_repo = ResellerRepository(session)
    reseller = await reseller_repo.get(SYSTEM_RESELLER_TG_ID)
    if reseller is None:
        raise XuiError("اکانت موردنظر برای تمدید یافت نشد.")
    try:
        xui = xui_for_record(panel_registry, record)
    except ServicePanelUnavailableError as e:
        raise XuiError(f"پنل اکانت ({e.panel_id}) در دسترس نیست.") from e

    plan_bytes = gb_to_bytes(volume_gb)
    await reseller_repo.add_quota_bytes(SYSTEM_RESELLER_TG_ID, plan_bytes)
    try:
        result = await ResellerService(session, xui).renew_service(
            reseller, record.email, volume_gb, expiry_days, extend_from_current=True
        )
    except Exception:
        await reseller_repo.add_quota_bytes(SYSTEM_RESELLER_TG_ID, -plan_bytes)
        raise
    await session.refresh(record)
    return record, result
