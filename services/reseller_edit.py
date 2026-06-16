"""Shared admin operations for editing reseller settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from db.models import Reseller
from db.repository import ResellerPanelRepository, ResellerRepository, resolve_attach_inbound_ids
from services.quota import QuotaService
from services.reseller_labels import reseller_label
from xui.client import bytes_to_gb, gb_to_bytes


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
    new_quota = gb_to_bytes(quota_gb)
    lifetime = int(row.lifetime_allocated_bytes or 0)
    if new_quota < lifetime:
        raise ValueError(
            f"سقف جدید ({quota_gb} GB) کمتر از مصرف/تخصیص فعلی "
            f"({bytes_to_gb(lifetime)} GB) است."
        )
    row = await repo.upsert(telegram_id, new_quota)
    return EditResult(
        reseller=row,
        message_text=t.QUOTA_UPDATED.format(
            label=reseller_label(row), quota_gb=quota_gb
        ),
    )


async def apply_add_quota(
    session: AsyncSession, telegram_id: int, add_gb: float
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.get(telegram_id)
    if not row:
        raise ResellerNotFoundError()
    if add_gb <= 0:
        raise ValueError("مقدار افزایش باید بزرگ‌تر از صفر باشد.")
    row = await repo.add_quota_bytes(telegram_id, gb_to_bytes(add_gb))
    assert row is not None
    return EditResult(
        reseller=row,
        message_text=t.QUOTA_ADDED.format(
            label=reseller_label(row),
            add_gb=add_gb,
            quota_gb=bytes_to_gb(row.quota_bytes),
        ),
    )


async def apply_subtract_quota(
    session: AsyncSession, telegram_id: int, subtract_gb: float
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.get(telegram_id)
    if not row:
        raise ResellerNotFoundError()
    if subtract_gb <= 0:
        raise ValueError("مقدار کاهش باید بزرگ‌تر از صفر باشد.")
    subtract_bytes = gb_to_bytes(subtract_gb)
    lifetime = int(row.lifetime_allocated_bytes or 0)
    new_quota = int(row.quota_bytes or 0) - subtract_bytes
    if new_quota < lifetime:
        raise ValueError(
            f"سقف جدید ({bytes_to_gb(new_quota)} GB) کمتر از مصرف/تخصیص فعلی "
            f"({bytes_to_gb(lifetime)} GB) است."
        )
    row = await repo.subtract_quota_bytes(telegram_id, subtract_bytes)
    assert row is not None
    return EditResult(
        reseller=row,
        message_text=t.QUOTA_SUBTRACTED.format(
            label=reseller_label(row),
            subtract_gb=subtract_gb,
            quota_gb=bytes_to_gb(row.quota_bytes),
        ),
    )


async def apply_reset_quota_usage(
    session: AsyncSession, telegram_id: int
) -> EditResult:
    repo = ResellerRepository(session)
    row = await repo.get(telegram_id)
    if not row:
        raise ResellerNotFoundError()
    row = await repo.reset_lifetime_to_active(telegram_id)
    assert row is not None
    st = await QuotaService(repo, ResellerPanelRepository(session)).global_status(row)
    return EditResult(
        reseller=row,
        message_text=t.QUOTA_USAGE_RESET.format(
            label=reseller_label(row),
            lifetime_gb=st.lifetime_gb,
            remaining_gb=st.remaining_gb,
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
    quota_svc = QuotaService(repo, ResellerPanelRepository(session))
    st = await quota_svc.global_status(row)
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
