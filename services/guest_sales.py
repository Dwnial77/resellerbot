"""Provisioning for guest self-service purchases via a hidden system reseller."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClientRecord, GuestOrder, GuestSalesConfig, Plan, Reseller
from db.repository import ResellerRepository, inbound_ids_from_json
from services.panel_registry import PanelRegistry
from services.panel_resolve import xui_for_reseller_panel
from services.reseller_service import ResellerService
from xui.client import ClientDelivery, gb_to_bytes

SYSTEM_RESELLER_TG_ID = 0
SYSTEM_RESELLER_DISPLAY_NAME = "guest-sales"


async def ensure_system_reseller(
    session: AsyncSession, panel_id: int, inbound_ids: list[int]
) -> Reseller:
    repo = ResellerRepository(session)
    existing = await repo.get(SYSTEM_RESELLER_TG_ID)
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


async def deliver_guest_order(
    session: AsyncSession,
    panel_registry: PanelRegistry,
    order: GuestOrder,
    plan: Plan,
    guest_config: GuestSalesConfig,
) -> tuple[ClientRecord, ClientDelivery]:
    assert guest_config.panel_id is not None
    inbound_ids = inbound_ids_from_json(guest_config.inbound_ids)
    reseller = await ensure_system_reseller(
        session, guest_config.panel_id, inbound_ids
    )
    reseller_repo = ResellerRepository(session)
    await reseller_repo.add_quota_bytes(
        SYSTEM_RESELLER_TG_ID, gb_to_bytes(plan.volume_gb)
    )
    reseller = await reseller_repo.get(SYSTEM_RESELLER_TG_ID) or reseller

    xui = await xui_for_reseller_panel(
        panel_registry, session, reseller, guest_config.panel_id
    )
    svc = ResellerService(session, xui)
    return await svc.create_service(
        reseller,
        volume_gb=plan.volume_gb,
        expiry_days=plan.expiry_days,
        client_suffix=f"guest{order.telegram_id}_{order.id}",
        panel_id=guest_config.panel_id,
        inbound_ids=inbound_ids,
    )
