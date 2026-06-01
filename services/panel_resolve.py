"""Resolve XuiClient for a client record's panel."""

from __future__ import annotations

from db.models import ClientRecord
from services.panel_registry import PanelNotFoundError, PanelRegistry
from xui.client import XuiClient


class ServiceNotFoundError(LookupError):
    pass


class ServicePanelUnavailableError(Exception):
    def __init__(self, panel_id: int) -> None:
        self.panel_id = panel_id
        super().__init__(panel_id)


def xui_for_record(registry: PanelRegistry, record: ClientRecord) -> XuiClient:
    try:
        return registry.get_client(record.panel_id)
    except PanelNotFoundError as e:
        raise ServicePanelUnavailableError(record.panel_id) from e


def list_accessible_panel_ids(registry: PanelRegistry) -> set[int]:
    return set(registry.loaded_panel_ids())
