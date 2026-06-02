"""Resolve XuiClient for reseller / client record panels."""

from __future__ import annotations

from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClientRecord, Reseller
from db.repository import PanelRepository
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


async def xui_for_reseller(
    registry: PanelRegistry,
    session: AsyncSession,
    reseller: Reseller,
) -> XuiClient:
    """Return XUI client for reseller's panel; reload registry from DB once if needed."""
    panel_row = await PanelRepository(session).get(reseller.panel_id)
    if panel_row is None:
        raise ResellerPanelUnavailableError(
            reseller.panel_id, ResellerPanelReason.MISSING
        )
    if not panel_row.is_active:
        raise ResellerPanelUnavailableError(
            reseller.panel_id,
            ResellerPanelReason.INACTIVE,
            panel_name=panel_row.name,
        )
    try:
        return registry.get_client(reseller.panel_id)
    except PanelNotFoundError:
        await registry.reload_panel(session, reseller.panel_id)
        try:
            return registry.get_client(reseller.panel_id)
        except PanelNotFoundError:
            raise ResellerPanelUnavailableError(
                reseller.panel_id,
                ResellerPanelReason.NOT_LOADED,
                panel_name=panel_row.name,
            ) from None


def xui_for_record(registry: PanelRegistry, record: ClientRecord) -> XuiClient:
    try:
        return registry.get_client(record.panel_id)
    except PanelNotFoundError as e:
        raise ServicePanelUnavailableError(record.panel_id) from e


def list_accessible_panel_ids(registry: PanelRegistry) -> set[int]:
    return set(registry.loaded_panel_ids())
