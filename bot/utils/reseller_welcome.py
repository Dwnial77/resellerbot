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
from services.quota import QuotaService
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
    client_count = 0
    lines: list[str] = []

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
        client_count += st.client_count
        default = " (پیش‌فرض)" if assignment.panel_id == reseller.panel_id else ""
        lines.append(
            f"• {name}{default}: {st.lifetime_gb:.1f}/{st.quota_gb:.1f} GB — "
            f"{st.client_count} سرویس"
        )

    if len(lines) <= 1:
        if lines:
            panel = await panel_repo.get(assignments[0].panel_id) if assignments else None
            st = await quota_svc.status(reseller, assignments[0].panel_id) if assignments else None
            if st is not None:
                from db.repository import format_inbound_summary_for_assignment

                inbounds = ""
                if assignments:
                    inbounds = format_inbound_summary_for_assignment(assignments[0])
                return t.WELCOME_RESELLER.format(
                    display_name=display_name,
                    panel_id=reseller.panel_id,
                    panel_name=panel.name if panel else f"#{reseller.panel_id}",
                    quota_gb=st.quota_gb,
                    active_gb=st.active_gb,
                    lifetime_gb=st.lifetime_gb,
                    remaining_gb=st.remaining_gb,
                    client_count=st.client_count,
                    max_clients_line=(
                        f"{st.max_clients} سرویس"
                        if st.max_clients is not None
                        else "نامحدود"
                    ),
                    inbounds_summary=inbounds,
                )

    return t.WELCOME_RESELLER_MULTI.format(
        display_name=display_name,
        panels_lines="\n".join(lines) if lines else "—",
        client_count=client_count,
    )
