"""Resolve XuiClient for reseller / client record panels."""

from __future__ import annotations

from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClientRecord, Reseller
from db.repository import PanelRepository, ResellerPanelRepository
from services.panel_registry import PanelNotFoundError, PanelRegistry
from xui.client import XuiClient


class ServiceNotFoundError(LookupError):
    pass


class ServicePanelUnavailableError(Exception):
    def __init__(self, panel_id: int) -> None:
        self.panel_id = panel_id
        super().__init__(panel_id)


class ResellerPanelReason(str, Enum):
    MISSING = "missing"
    INACTIVE = "inactive"
    NOT_LOADED = "not_loaded"
    NOT_ASSIGNED = "not_assigned"
    ASSIGNMENT_INACTIVE = "assignment_inactive"


class ResellerPanelUnavailableError(Exception):
    def __init__(
        self,
        panel_id: int,
        reason: ResellerPanelReason,
        *,
        panel_name: str | None = None,
    ) -> None:
        self.panel_id = panel_id
        self.reason = reason
        self.panel_name = panel_name
        super().__init__(panel_id)


async def _xui_for_panel_id(
    registry: PanelRegistry,
    session: AsyncSession,
    panel_id: int,
) -> XuiClient:
    panel_row = await PanelRepository(session).get(panel_id)
    if panel_row is None:
        raise ResellerPanelUnavailableError(
            panel_id, ResellerPanelReason.MISSING
        )
    if not panel_row.is_active:
        raise ResellerPanelUnavailableError(
            panel_id,
            ResellerPanelReason.INACTIVE,
            panel_name=panel_row.name,
        )
    try:
        return registry.get_client(panel_id)
    except PanelNotFoundError:
        await registry.reload_panel(session, panel_id)
        try:
            return registry.get_client(panel_id)
        except PanelNotFoundError:
            raise ResellerPanelUnavailableError(
                panel_id,
                ResellerPanelReason.NOT_LOADED,
                panel_name=panel_row.name,
            ) from None


async def xui_for_reseller_panel(
    registry: PanelRegistry,
    session: AsyncSession,
    reseller: Reseller,
    panel_id: int,
) -> XuiClient:
    """Return XUI client for a panel assigned to reseller."""
    assignment = await ResellerPanelRepository(session).get(
        reseller.telegram_id, panel_id
    )
    if assignment is None:
        raise ResellerPanelUnavailableError(
            panel_id, ResellerPanelReason.NOT_ASSIGNED
        )
    if not assignment.is_active:
        raise ResellerPanelUnavailableError(
            panel_id, ResellerPanelReason.ASSIGNMENT_INACTIVE
        )
    return await _xui_for_panel_id(registry, session, panel_id)


async def xui_for_reseller(
    registry: PanelRegistry,
    session: AsyncSession,
    reseller: Reseller,
) -> XuiClient:
    """Return XUI client for reseller's default panel."""
    return await xui_for_reseller_panel(
        registry, session, reseller, reseller.panel_id
    )


def xui_for_record(registry: PanelRegistry, record: ClientRecord) -> XuiClient:
    try:
        return registry.get_client(record.panel_id)
    except PanelNotFoundError as e:
        raise ServicePanelUnavailableError(record.panel_id) from e


def list_accessible_panel_ids(registry: PanelRegistry) -> set[int]:
    return set(registry.loaded_panel_ids())


async def list_reseller_panel_ids(
    session: AsyncSession, reseller: Reseller, *, active_only: bool = True
) -> list[int]:
    return await ResellerPanelRepository(session).list_active_panel_ids(
        reseller.telegram_id
    ) if active_only else [
        r.panel_id
        for r in await ResellerPanelRepository(session).list_for_reseller(
            reseller.telegram_id
        )
    ]
