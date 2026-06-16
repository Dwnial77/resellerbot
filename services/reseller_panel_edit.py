"""Admin operations for per-panel reseller assignments."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from db.models import Panel, Reseller, ResellerPanel
from db.repository import (
    PanelRepository,
    ResellerPanelRepository,
    ResellerRepository,
    inbound_ids_from_json,
    resolve_attach_inbound_ids_for_assignment,
)
from services.quota import QuotaService
from services.reseller_labels import reseller_label
from xui.client import bytes_to_gb, gb_to_bytes


class ResellerNotFoundError(LookupError):
    pass


class PanelNotFoundError(LookupError):
    pass


class AssignmentNotFoundError(LookupError):
    pass


@dataclass
class PanelEditResult:
    assignment: ResellerPanel
    panel: Panel
    message_text: str


async def _get_assignment(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> tuple[ResellerPanel, Panel]:
    reseller_repo = ResellerRepository(session)
    panel_repo = ResellerPanelRepository(session)
    panels = PanelRepository(session)
    reseller = await reseller_repo.get(telegram_id)
    if not reseller:
        raise ResellerNotFoundError()
    assignment = await panel_repo.get(telegram_id, panel_id)
    if not assignment:
        raise AssignmentNotFoundError()
    panel = await panels.get(panel_id)
    if not panel:
        raise PanelNotFoundError()
    return assignment, panel


async def apply_panel_quota(
    session: AsyncSession, telegram_id: int, panel_id: int, quota_gb: float
) -> PanelEditResult:
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    panel_repo = ResellerPanelRepository(session)
    row = await panel_repo.set_quota_bytes(
        telegram_id, panel_id, gb_to_bytes(quota_gb)
    )
    assert row is not None
    reseller = await ResellerRepository(session).get(telegram_id)
    if reseller and reseller.panel_id == panel_id:
        reseller.quota_bytes = row.quota_bytes
        await session.commit()
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_QUOTA_UPDATED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
            quota_gb=quota_gb,
        ),
    )


async def apply_panel_add_quota(
    session: AsyncSession, telegram_id: int, panel_id: int, add_gb: float
) -> PanelEditResult:
    if add_gb <= 0:
        raise ValueError("مقدار افزایش باید بزرگ‌تر از صفر باشد.")
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    panel_repo = ResellerPanelRepository(session)
    row = await panel_repo.add_quota_bytes(
        telegram_id, panel_id, gb_to_bytes(add_gb)
    )
    assert row is not None
    reseller = await ResellerRepository(session).get(telegram_id)
    if reseller and reseller.panel_id == panel_id:
        await ResellerRepository(session).add_quota_bytes(
            telegram_id, gb_to_bytes(add_gb)
        )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_QUOTA_ADDED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
            add_gb=add_gb,
            quota_gb=bytes_to_gb(row.quota_bytes),
        ),
    )


async def apply_panel_reset_quota_usage(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> PanelEditResult:
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    reseller_repo = ResellerRepository(session)
    panel_repo = ResellerPanelRepository(session)
    active = await reseller_repo.active_bytes_on_panel(telegram_id, panel_id)
    row = await panel_repo.reset_lifetime_to_active(
        telegram_id, panel_id, active
    )
    assert row is not None
    reseller = await reseller_repo.get(telegram_id)
    if reseller and reseller.panel_id == panel_id:
        await reseller_repo.reset_lifetime_to_active(telegram_id)
    st = await QuotaService(reseller_repo, panel_repo).status(
        reseller, panel_id  # type: ignore[arg-type]
    )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_QUOTA_USAGE_RESET.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
            lifetime_gb=st.lifetime_gb,
            remaining_gb=st.remaining_gb,
        ),
    )


async def apply_panel_allowed_inbounds(
    session: AsyncSession, telegram_id: int, panel_id: int, inbound_ids: list[int]
) -> PanelEditResult:
    panel_repo = ResellerPanelRepository(session)
    row, trimmed = await panel_repo.set_allowed_inbound_ids(
        telegram_id, panel_id, inbound_ids
    )
    if not row:
        raise AssignmentNotFoundError()
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    reseller = await ResellerRepository(session).get(telegram_id)
    if reseller and reseller.panel_id == panel_id:
        await ResellerRepository(session).set_allowed_inbound_ids(
            telegram_id, inbound_ids
        )
    allowed_s = ", ".join(str(i) for i in inbound_ids)
    attach_s = ", ".join(
        str(i) for i in resolve_attach_inbound_ids_for_assignment(row)
    )
    warning = ""
    if trimmed:
        warning = (
            "\n\nتوجه: اینباندهای متصل هم با مجاز جدید یکسان شد."
        )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_ALLOWED_INBOUNDS_UPDATED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
            allowed_inbounds=allowed_s,
            attach_inbounds=attach_s,
            warning=warning,
        ),
    )


async def apply_panel_attach_inbounds(
    session: AsyncSession, telegram_id: int, panel_id: int, inbound_ids: list[int]
) -> PanelEditResult:
    panel_repo = ResellerPanelRepository(session)
    row = await panel_repo.set_attach_inbound_ids(
        telegram_id, panel_id, inbound_ids
    )
    if not row:
        raise AssignmentNotFoundError()
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    reseller = await ResellerRepository(session).get(telegram_id)
    if reseller and reseller.panel_id == panel_id:
        await ResellerRepository(session).set_attach_inbound_ids(
            telegram_id, inbound_ids
        )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_ATTACH_INBOUNDS_UPDATED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
            attach_inbounds=", ".join(str(i) for i in inbound_ids),
        ),
    )


async def apply_panel_max_clients(
    session: AsyncSession, telegram_id: int, panel_id: int, max_clients: int
) -> PanelEditResult:
    panel_repo = ResellerPanelRepository(session)
    reseller_repo = ResellerRepository(session)
    reseller = await reseller_repo.get(telegram_id)
    if not reseller:
        raise ResellerNotFoundError()
    st = await QuotaService(reseller_repo, panel_repo).status(reseller, panel_id)
    row = await panel_repo.set_max_clients(telegram_id, panel_id, max_clients)
    assert row is not None
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    if reseller.panel_id == panel_id:
        await reseller_repo.set_max_clients(telegram_id, max_clients)
    warning = ""
    if st.client_count > max_clients:
        warning = (
            f"\n\nتوجه: روی این پنل {st.client_count} سرویس فعال است؛ "
            "ساخت جدید مسدود است."
        )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_MAX_CLIENTS_UPDATED.format(
            label=reseller_label(reseller),
            panel_name=panel.name,
            max_clients=max_clients,
            warning=warning,
        ),
    )


async def apply_add_panel_assignment(
    session: AsyncSession,
    telegram_id: int,
    panel_id: int,
    allowed_inbound_ids: list[int],
    *,
    attach_inbound_ids: list[int] | None = None,
    max_clients: int | None = None,
) -> PanelEditResult:
    reseller = await ResellerRepository(session).get(telegram_id)
    if not reseller:
        raise ResellerNotFoundError()
    panel = await PanelRepository(session).get(panel_id)
    if not panel:
        raise PanelNotFoundError()
    row = await ResellerPanelRepository(session).add(
        telegram_id,
        panel_id,
        0,
        allowed_inbound_ids,
        attach_inbound_ids=attach_inbound_ids,
        max_clients=max_clients,
    )
    return PanelEditResult(
        assignment=row,
        panel=panel,
        message_text=t.PANEL_ASSIGNMENT_ADDED.format(
            label=reseller_label(reseller),
            panel_name=panel.name,
        ),
    )


async def apply_remove_panel_assignment(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> PanelEditResult:
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    reseller = await ResellerRepository(session).get(telegram_id)
    await ResellerPanelRepository(session).delete(telegram_id, panel_id)
    return PanelEditResult(
        assignment=assignment,
        panel=panel,
        message_text=t.PANEL_ASSIGNMENT_REMOVED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
        ),
    )


async def apply_panel_toggle_create_allowed(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> PanelEditResult:
    assignment, panel = await _get_assignment(session, telegram_id, panel_id)
    panel_repo = ResellerPanelRepository(session)
    new_active = not assignment.is_active
    row = await panel_repo.set_active(telegram_id, panel_id, new_active)
    assert row is not None
    reseller = await ResellerRepository(session).get(telegram_id)
    if new_active:
        msg = t.PANEL_CREATE_ALLOWED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
        )
    else:
        msg = t.PANEL_CREATE_BLOCKED.format(
            label=reseller_label(reseller) if reseller else str(telegram_id),
            panel_name=panel.name,
        )
    return PanelEditResult(assignment=row, panel=panel, message_text=msg)


async def apply_set_default_panel(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> PanelEditResult:
    reseller = await ResellerRepository(session).get(telegram_id)
    if not reseller:
        raise ResellerNotFoundError()
    assignment = await ResellerPanelRepository(session).get(
        telegram_id, panel_id
    )
    if not assignment:
        raise AssignmentNotFoundError()
    panel = await PanelRepository(session).get(panel_id)
    if not panel:
        raise PanelNotFoundError()
    reseller.panel_id = panel_id
    reseller.allowed_inbound_ids = assignment.allowed_inbound_ids
    reseller.attach_inbound_ids = assignment.attach_inbound_ids
    reseller.max_clients = assignment.max_clients
    await session.commit()
    await session.refresh(reseller)
    return PanelEditResult(
        assignment=assignment,
        panel=panel,
        message_text=t.DEFAULT_PANEL_SET.format(
            label=reseller_label(reseller),
            panel_name=panel.name,
        ),
    )
