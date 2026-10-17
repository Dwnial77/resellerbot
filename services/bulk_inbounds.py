"""Bulk inbound enable/disable across every reseller on one panel.

Adding an inbound in 3x-ui otherwise means editing each reseller by hand. This
also carries the diagnosis for the inverse problem: a reseller row still
pointing at an inbound that no longer exists on the panel, which makes service
creation fail with the panel's opaque "record not found".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResellerPanel
from db.repository import (
    ResellerPanelRepository,
    ResellerRepository,
    inbound_ids_from_json,
    inbound_ids_to_json,
    resolve_attach_inbound_ids_for_assignment,
)
from services.reseller_labels import reseller_label

logger = logging.getLogger(__name__)

SKIP_LAST_INBOUND = "تنها اینباند باقی‌مانده‌اش بود"
SKIP_ALREADY = "از قبل همین وضعیت را داشت"


@dataclass
class BulkInboundResult:
    inbound_id: int
    enabled: bool
    updated: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return len(self.updated)


@dataclass
class InboundDiagnosis:
    label: str
    missing_allowed: list[int]
    missing_attach: list[int]
    fully_blocked: bool


async def _label_for(session: AsyncSession, telegram_id: int) -> str:
    reseller = await ResellerRepository(session).get(telegram_id)
    return reseller_label(reseller) if reseller else str(telegram_id)


def _assignment_lists(row: ResellerPanel) -> tuple[list[int], list[int]]:
    return (
        inbound_ids_from_json(row.allowed_inbound_ids),
        resolve_attach_inbound_ids_for_assignment(row),
    )


async def _sync_legacy_row(
    session: AsyncSession,
    telegram_id: int,
    panel_id: int,
    allowed: list[int],
    attach: list[int],
) -> None:
    """Mirror onto `resellers` when this is the reseller's default panel.

    Written field by field rather than through the repository setters, which
    force attach to equal allowed and would drop a narrowed attach list.
    """
    reseller = await ResellerRepository(session).get(telegram_id)
    if reseller is None or reseller.panel_id != panel_id:
        return
    reseller.allowed_inbound_ids = inbound_ids_to_json(allowed)
    reseller.attach_inbound_ids = inbound_ids_to_json(attach)


async def apply_bulk_inbound(
    session: AsyncSession,
    panel_id: int,
    inbound_id: int,
    *,
    enable: bool,
) -> BulkInboundResult:
    """Add or remove one inbound for every reseller assigned to `panel_id`.

    Allowed and attach move together. A reseller whose list would end up empty
    is left untouched and reported, so one edge case cannot block the rest.
    """
    repo = ResellerPanelRepository(session)
    result = BulkInboundResult(inbound_id=inbound_id, enabled=enable)

    for row in await repo.list_for_panel(panel_id):
        allowed, attach = _assignment_lists(row)
        label = await _label_for(session, row.reseller_tg_id)

        if enable:
            if inbound_id in allowed and inbound_id in attach:
                result.skipped.append((label, SKIP_ALREADY))
                continue
            new_allowed = sorted(set(allowed) | {inbound_id})
            # Preserve a narrowed attach list: only add, never reset to allowed.
            new_attach = sorted(set(attach) | {inbound_id})
        else:
            if inbound_id not in allowed and inbound_id not in attach:
                result.skipped.append((label, SKIP_ALREADY))
                continue
            new_allowed = sorted(set(allowed) - {inbound_id})
            new_attach = sorted(set(attach) - {inbound_id})
            if not new_allowed or not new_attach:
                result.skipped.append((label, SKIP_LAST_INBOUND))
                continue

        row.allowed_inbound_ids = inbound_ids_to_json(new_allowed)
        row.attach_inbound_ids = inbound_ids_to_json(new_attach)
        await _sync_legacy_row(
            session, row.reseller_tg_id, panel_id, new_allowed, new_attach
        )
        # Commit per reseller so one failure cannot roll back the others.
        await session.commit()
        result.updated.append(label)

    logger.info(
        "Bulk inbound %s on panel #%s inbound %s: %d updated, %d skipped",
        "enable" if enable else "disable",
        panel_id,
        inbound_id,
        len(result.updated),
        len(result.skipped),
    )
    return result


async def count_resellers_with_inbound(
    session: AsyncSession, panel_id: int, inbound_id: int
) -> tuple[int, int]:
    """(resellers already holding this inbound, total resellers on the panel)."""
    rows = await ResellerPanelRepository(session).list_for_panel(panel_id)
    have = sum(1 for r in rows if inbound_id in inbound_ids_from_json(r.allowed_inbound_ids))
    return have, len(rows)


async def orphan_inbound_ids(
    session: AsyncSession, panel_id: int, live_inbound_ids: set[int]
) -> list[int]:
    """Inbound ids reseller rows still reference but the panel no longer has.

    These are exactly the ids that make service creation fail, and they cannot
    be selected from the panel's own inbound list, so the bulk screen has to
    surface them separately.
    """
    orphans: set[int] = set()
    for row in await ResellerPanelRepository(session).list_for_panel(panel_id):
        allowed, attach = _assignment_lists(row)
        orphans |= (set(allowed) | set(attach)) - live_inbound_ids
    return sorted(orphans)


async def diagnose_panel_inbounds(
    session: AsyncSession, panel_id: int, live_inbound_ids: set[int]
) -> list[InboundDiagnosis]:
    """Reseller rows referencing inbounds the panel no longer has.

    `live_inbound_ids` must come from a successful `list_inbounds()` call. Never
    call this with an empty set from a failed request — every reseller would
    look broken when the real fault is an unreachable panel.
    """
    out: list[InboundDiagnosis] = []
    for row in await ResellerPanelRepository(session).list_for_panel(panel_id):
        allowed, attach = _assignment_lists(row)
        missing_allowed = sorted(set(allowed) - live_inbound_ids)
        missing_attach = sorted(set(attach) - live_inbound_ids)
        if not missing_allowed and not missing_attach:
            continue
        out.append(
            InboundDiagnosis(
                label=await _label_for(session, row.reseller_tg_id),
                missing_allowed=missing_allowed,
                missing_attach=missing_attach,
                # No usable inbound left => cannot create any service at all.
                fully_blocked=not (set(attach) & live_inbound_ids),
            )
        )
    return out
