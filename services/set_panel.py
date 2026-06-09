"""Set reseller default panel (must already be assigned)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Panel, Reseller
from db.repository import PanelRepository, ResellerRepository
from services.reseller_panel_edit import (
    AssignmentNotFoundError,
    PanelNotFoundError as AssignmentPanelNotFoundError,
    ResellerNotFoundError as AssignmentResellerNotFoundError,
    apply_set_default_panel,
)


class ResellerNotFoundError(LookupError):
    pass


class PanelNotFoundError(LookupError):
    pass


class SetPanelBlockedError(ValueError):
    """Panel is not assigned to reseller."""

    def __init__(self, panel_id: int) -> None:
        self.panel_id = panel_id
        super().__init__(panel_id)


@dataclass
class SetPanelResult:
    reseller: Reseller
    panel: Panel
    unchanged: bool


async def apply_reseller_panel(
    session: AsyncSession, telegram_id: int, panel_id: int
) -> SetPanelResult:
    reseller_repo = ResellerRepository(session)
    reseller = await reseller_repo.get(telegram_id)
    if reseller is None:
        raise ResellerNotFoundError()
    if reseller.panel_id == panel_id:
        panel = await PanelRepository(session).get(panel_id)
        if panel is None:
            raise PanelNotFoundError()
        return SetPanelResult(reseller=reseller, panel=panel, unchanged=True)

    try:
        result = await apply_set_default_panel(session, telegram_id, panel_id)
    except AssignmentResellerNotFoundError:
        raise ResellerNotFoundError() from None
    except AssignmentPanelNotFoundError:
        raise PanelNotFoundError() from None
    except AssignmentNotFoundError:
        raise SetPanelBlockedError(panel_id) from None

    updated = await reseller_repo.get(telegram_id)
    assert updated is not None
    return SetPanelResult(
        reseller=updated, panel=result.panel, unchanged=False
    )
