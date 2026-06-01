"""Apply reseller panel assignment with validation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Panel, Reseller
from db.repository import PanelRepository, ResellerRepository


class ResellerNotFoundError(LookupError):
    pass


class PanelNotFoundError(LookupError):
    pass


class SetPanelBlockedError(ValueError):
    """Reseller has clients; panel cannot be changed."""

    def __init__(self, client_count: int) -> None:
        self.client_count = client_count
        super().__init__(client_count)


@dataclass
class SetPanelResult:
    reseller: Reseller
    panel: Panel
    unchanged: bool


async def apply_reseller_panel(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> SetPanelResult:
    panel_repo = PanelRepository(session)
    reseller_repo = ResellerRepository(session)

    panel = await panel_repo.get(panel_id)
    if panel is None:
        raise PanelNotFoundError()

    reseller = await reseller_repo.get(telegram_id)
    if reseller is None:
        raise ResellerNotFoundError()

    if reseller.panel_id == panel_id:
        return SetPanelResult(reseller=reseller, panel=panel, unchanged=True)

    client_count = await reseller_repo.client_count(telegram_id)
    if client_count > 0:
        raise SetPanelBlockedError(client_count)

    updated = await reseller_repo.set_panel_id(telegram_id, panel_id)
    assert updated is not None
    return SetPanelResult(reseller=updated, panel=panel, unchanged=False)
