"""Build reseller welcome / account status text for multi-panel assignments."""

from __future__ import annotations

from db.models import Reseller
from db.repository import PanelRepository, ResellerPanelRepository, ResellerRepository
from services.panel_registry import PanelRegistry
from services.panel_resolve import (
    ResellerPanelUnavailableError,
    list_reseller_panel_ids,
    xui_for_reseller_panel,
)
from services.quota import QuotaService, format_max_clients_line
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t


async def accessible_panel_ids(
    registry: PanelRegistry, session: AsyncSession, reseller: Reseller
) -> list[int]:
    out: list[int] = []
    for panel_id in await list_reseller_panel_ids(session, reseller):
        try:
            await xui_for_reseller_panel(registry, session, reseller, panel_id)
            out.append(panel_id)
        except ResellerPanelUnavailableError:
            continue
    return out


async def format_reseller_welcome(
    session: AsyncSession,
    reseller: Reseller,
    *,
    registry: PanelRegistry | None = None,
) -> str:
    panel_repo = PanelRepository(session)
    assign_repo = ResellerPanelRepository(session)
    quota_svc = QuotaService(ResellerRepository(session), assign_repo)
    assignments = await assign_repo.list_for_reseller(reseller.telegram_id)
    display_name = f" {reseller.display_name}" if reseller.display_name else ""
    global_st = await quota_svc.global_status(reseller)
    panel_lines: list[str] = []

    for assignment in assignments:
        if registry is not None:
            try:
                await xui_for_reseller_panel(
                    registry, session, reseller, assignment.panel_id
                )
            except ResellerPanelUnavailableError:
                continue
        panel = await panel_repo.get(assignment.panel_id)
        name = panel.name if panel else f"#{assignment.panel_id}"
        st = await quota_svc.status(reseller, assignment.panel_id)
        default = " (پیش‌فرض)" if assignment.panel_id == reseller.panel_id else ""
        panel_lines.append(
            f"• {name}{default}: {st.client_count} سرویس"
        )

    quota_block = (
        f"سقف حجم کل: {global_st.quota_gb} GB\n"
        f"تخصیص فعال: {global_st.active_gb} GB\n"
        f"مصرف سهمیه: {global_st.lifetime_gb} GB\n"
        f"باقی‌مانده: {global_st.remaining_gb} GB\n"
        f"تعداد سرویس: {global_st.client_count}"
    )

    if len(panel_lines) <= 1 and assignments:
        from db.repository import format_inbound_summary_for_assignment

        inbounds = format_inbound_summary_for_assignment(assignments[0])
        panel = await panel_repo.get(assignments[0].panel_id)
        st = await quota_svc.status(reseller, assignments[0].panel_id)
        return t.WELCOME_RESELLER.format(
            display_name=display_name,
            panel_id=reseller.panel_id,
            panel_name=panel.name if panel else f"#{reseller.panel_id}",
            quota_gb=global_st.quota_gb,
            active_gb=global_st.active_gb,
            lifetime_gb=global_st.lifetime_gb,
            remaining_gb=global_st.remaining_gb,
            client_count=global_st.client_count,
            max_clients_line=format_max_clients_line(st),
            inbounds_summary=inbounds,
        )

    return t.WELCOME_RESELLER_MULTI.format(
        display_name=display_name,
        quota_block=quota_block,
        panels_lines="\n".join(panel_lines) if panel_lines else "—",
        client_count=global_st.client_count,
    )
