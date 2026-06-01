"""Shared admin operations for editing reseller settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from db.models import Reseller
from db.repository import ResellerRepository, resolve_attach_inbound_ids
from services.quota import QuotaService
from services.reseller_labels import reseller_label
from xui.client import gb_to_bytes


class ResellerNotFoundError(LookupError):
    pass


@dataclass
class EditResult:
    reseller: Reseller
    message_text: str


async def apply_quota(
    session: AsyncSession, telegram_id: int, quota_gb: float
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.get(telegram_id)
    if not row:
        raise ResellerNotFoundError()
    row = await repo.upsert(telegram_id, gb_to_bytes(quota_gb))
    return EditResult(
        reseller=row,
        message_text=t.QUOTA_UPDATED.format(
            label=reseller_label(row), quota_gb=quota_gb
        ),
    )


async def apply_display_name(
    session: AsyncSession, telegram_id: int, display_name: str
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.set_display_name(telegram_id, display_name)
    if not row:
        raise ResellerNotFoundError()
    return EditResult(
        reseller=row,
        message_text=t.NAME_UPDATED.format(label=reseller_label(row)),
    )


async def apply_max_clients(
    session: AsyncSession, telegram_id: int, max_clients: int
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.get(telegram_id)
    if not row:
        raise ResellerNotFoundError()
    quota_svc = QuotaService(repo)
    st = await quota_svc.status(row)
    row = await repo.set_max_clients(telegram_id, max_clients)
    assert row is not None
    warning = ""
    if st.client_count > max_clients:
        warning = (
            f"\n\nتوجه: این ریسلر الان {st.client_count} سرویس دارد؛ "
            "ساخت جدید مسدود است."
        )
    return EditResult(
        reseller=row,
        message_text=t.MAX_CLIENTS_UPDATED.format(
            label=reseller_label(row),
            max_clients=max_clients,
            warning=warning,
        ),
    )


async def clear_max_clients_limit(
    session: AsyncSession, telegram_id: int
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.set_max_clients(telegram_id, None)
    if not row:
        raise ResellerNotFoundError()
    return EditResult(
        reseller=row,
        message_text=t.MAX_CLIENTS_CLEARED.format(label=reseller_label(row)),
    )


async def apply_allowed_inbounds(
    session: AsyncSession, telegram_id: int, inbound_ids: list[int]
) -> EditResult:
    repo = ResellerRepository(session)
    try:
        row, trimmed = await repo.set_allowed_inbound_ids(telegram_id, inbound_ids)
    except ValueError:
        raise
    if not row:
        raise ResellerNotFoundError()
    allowed_s = ", ".join(str(i) for i in inbound_ids)
    attach_s = ", ".join(str(i) for i in resolve_attach_inbound_ids(row))
    warning = ""
    if trimmed:
        warning = (
            "\n\nتوجه: اینباندهای متصل هم با مجاز جدید یکسان شد. "
            "برای زیرمجموعه از ویرایش «اینباندهای متصل» استفاده کنید."
        )
    return EditResult(
        reseller=row,
        message_text=t.ALLOWED_INBOUNDS_UPDATED.format(
            label=reseller_label(row),
            allowed_inbounds=allowed_s,
            attach_inbounds=attach_s,
            warning=warning,
        ),
    )


async def apply_attach_inbounds(
    session: AsyncSession, telegram_id: int, inbound_ids: list[int]
) -> EditResult:
    repo = ResellerRepository(session)
    try:
        row = await repo.set_attach_inbound_ids(telegram_id, inbound_ids)
    except ValueError:
        raise
    if not row:
        raise ResellerNotFoundError()
    return EditResult(
        reseller=row,
        message_text=t.ATTACH_INBOUNDS_UPDATED.format(
            label=reseller_label(row),
            attach_inbounds=", ".join(str(i) for i in inbound_ids),
        ),
    )
