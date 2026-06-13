import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.panel_url import normalize_http_url, normalize_sub_public_url
from db.models import (
    ClientRecord,
    Panel,
    Reseller,
    ResellerPanel,
    ServiceTemplate,
    UsageAlertSent,
)

_MAX_TEMPLATE_NAME_LEN = 64


class InvalidTemplateError(ValueError):
    pass


def normalize_template_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise InvalidTemplateError("نام قالب نمی‌تواند خالی باشد.")
    if len(name) > _MAX_TEMPLATE_NAME_LEN:
        raise InvalidTemplateError(
            f"نام قالب حداکثر {_MAX_TEMPLATE_NAME_LEN} کاراکتر باشد."
        )
    return name


def validate_template_params(volume_gb: float, expiry_days: int) -> None:
    if volume_gb <= 0:
        raise InvalidTemplateError("حجم باید بزرگ‌تر از صفر باشد.")
    if expiry_days < 0:
        raise InvalidTemplateError("روز انقضا نمی‌تواند منفی باشد.")

_UNSET_MAX_CLIENTS: object = object()
_UNSET_INBOUNDS: object = object()


def inbound_ids_to_json(ids: list[int]) -> str:
    return json.dumps(ids)


def inbound_ids_from_json(raw: str | None) -> list[int]:
    if not raw:
        return []
    return json.loads(raw)


def resolve_attach_inbound_ids(reseller: Reseller) -> list[int]:
    attach = inbound_ids_from_json(reseller.attach_inbound_ids)
    if attach:
        return attach
    return inbound_ids_from_json(reseller.allowed_inbound_ids)


def resolve_attach_inbound_ids_for_assignment(assignment: ResellerPanel) -> list[int]:
    attach = inbound_ids_from_json(assignment.attach_inbound_ids)
    if attach:
        return attach
    return inbound_ids_from_json(assignment.allowed_inbound_ids)


def format_inbound_summary_for_assignment(assignment: ResellerPanel) -> str:
    allowed = inbound_ids_from_json(assignment.allowed_inbound_ids)
    attach = resolve_attach_inbound_ids_for_assignment(assignment)
    attach_s = ", ".join(str(i) for i in attach)
    if sorted(attach) == sorted(allowed):
        return f"اینباندهای متصل: {attach_s}"
    allowed_s = ", ".join(str(i) for i in allowed)
    return f"اینباندهای متصل: {attach_s}\nاینباندهای مجاز: {allowed_s}"


def validate_inbound_subset(allowed: list[int], attach: list[int]) -> None:
    if not attach:
        raise ValueError("لیست اینباندهای متصل نمی‌تواند خالی باشد.")
    allowed_set = set(allowed)
    if not allowed_set:
        raise ValueError("لیست اینباندهای مجاز نمی‌تواند خالی باشد.")
    extra = set(attach) - allowed_set
    if extra:
        raise ValueError(
            f"اینباندهای {sorted(extra)} در لیست مجاز نیستند."
        )


def format_inbound_summary(reseller: Reseller) -> str:
    allowed = inbound_ids_from_json(reseller.allowed_inbound_ids)
    attach = resolve_attach_inbound_ids(reseller)
    attach_s = ", ".join(str(i) for i in attach)
    if sorted(attach) == sorted(allowed):
        return f"اینباندهای متصل: {attach_s}"
    allowed_s = ", ".join(str(i) for i in allowed)
    return f"اینباندهای متصل: {attach_s}\nاینباندهای مجاز: {allowed_s}"


def trim_attach_to_allowed(allowed: list[int], attach: list[int]) -> list[int]:
    allowed_set = set(allowed)
    trimmed = [i for i in attach if i in allowed_set]
    return trimmed if trimmed else list(allowed)


class ResellerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, telegram_id: int) -> Reseller | None:
        return await self.session.get(Reseller, telegram_id)

    async def list_all(self) -> list[Reseller]:
        result = await self.session.scalars(select(Reseller).order_by(Reseller.created_at))
        return list(result.all())

    async def list_active(self) -> list[Reseller]:
        result = await self.session.scalars(
            select(Reseller)
            .where(Reseller.is_active.is_(True))
            .order_by(Reseller.created_at)
        )
        return list(result.all())

    async def upsert(
        self,
        telegram_id: int,
        quota_bytes: int,
        allowed_inbound_ids: list[int] | object = _UNSET_INBOUNDS,
        *,
        panel_id: int = 1,
        attach_inbound_ids: list[int] | object = _UNSET_INBOUNDS,
        display_name: str | None = None,
        is_active: bool = True,
        max_clients: int | None | object = _UNSET_MAX_CLIENTS,
    ) -> Reseller:
        row = await self.get(telegram_id)
        if row is None and allowed_inbound_ids is _UNSET_INBOUNDS:
            raise ValueError("allowed_inbound_ids required for new reseller")
        resolved_max: int | None
        if max_clients is _UNSET_MAX_CLIENTS:
            resolved_max = None if row is None else row.max_clients
        else:
            resolved_max = max_clients  # type: ignore[assignment]

        if allowed_inbound_ids is not _UNSET_INBOUNDS:
            allowed_list: list[int] = allowed_inbound_ids  # type: ignore[assignment]
            if not allowed_list:
                raise ValueError("لیست اینباندهای مجاز نمی‌تواند خالی باشد.")
            allowed_json = inbound_ids_to_json(allowed_list)
        else:
            allowed_json = None

        if attach_inbound_ids is not _UNSET_INBOUNDS:
            attach_list: list[int] = attach_inbound_ids  # type: ignore[assignment]
            if allowed_inbound_ids is _UNSET_INBOUNDS and row is not None:
                allowed_for_validate = inbound_ids_from_json(row.allowed_inbound_ids)
            else:
                allowed_for_validate = allowed_list  # type: ignore[possibly-undefined]
            validate_inbound_subset(allowed_for_validate, attach_list)
            attach_json = inbound_ids_to_json(attach_list)
        else:
            attach_json = None

        if row:
            row.quota_bytes = quota_bytes
            row.is_active = is_active
            if allowed_json is not None:
                row.allowed_inbound_ids = allowed_json
            if attach_json is not None:
                row.attach_inbound_ids = attach_json
            if max_clients is not _UNSET_MAX_CLIENTS:
                row.max_clients = resolved_max
            if display_name is not None:
                row.display_name = display_name
        else:
            assert allowed_json is not None
            if attach_json is None:
                attach_json = allowed_json
            row = Reseller(
                telegram_id=telegram_id,
                panel_id=panel_id,
                display_name=display_name,
                quota_bytes=quota_bytes,
                allowed_inbound_ids=allowed_json,
                attach_inbound_ids=attach_json,
                is_active=is_active,
                max_clients=resolved_max,
            )
            self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row

    async def _sync_primary_panel_assignment(self, row: Reseller) -> None:
        panel_repo = ResellerPanelRepository(self.session)
        assignment = await panel_repo.get(row.telegram_id, row.panel_id)
        if assignment is None:
            await panel_repo.add(
                row.telegram_id,
                row.panel_id,
                row.quota_bytes,
                inbound_ids_from_json(row.allowed_inbound_ids),
                attach_inbound_ids=inbound_ids_from_json(row.attach_inbound_ids),
                max_clients=row.max_clients,
                is_active=True,
            )
        else:
            assignment.quota_bytes = row.quota_bytes
            assignment.lifetime_allocated_bytes = row.lifetime_allocated_bytes
            assignment.allowed_inbound_ids = row.allowed_inbound_ids
            assignment.attach_inbound_ids = row.attach_inbound_ids
            assignment.max_clients = row.max_clients
            await self.session.commit()

    async def set_allowed_inbound_ids(
        self, telegram_id: int, allowed: list[int]
    ) -> tuple[Reseller | None, bool]:
        """Set allowed inbounds; attach is synced to the same list (use set_attach to narrow)."""
        row = await self.get(telegram_id)
        if not row:
            return None, False
        if not allowed:
            raise ValueError("لیست اینباندهای مجاز نمی‌تواند خالی باشد.")
        old_attach = resolve_attach_inbound_ids(row)
        row.allowed_inbound_ids = inbound_ids_to_json(allowed)
        row.attach_inbound_ids = inbound_ids_to_json(allowed)
        was_trimmed = set(old_attach) != set(allowed)
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row, was_trimmed

    async def set_attach_inbound_ids(
        self, telegram_id: int, attach: list[int]
    ) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        allowed = inbound_ids_from_json(row.allowed_inbound_ids)
        validate_inbound_subset(allowed, attach)
        row.attach_inbound_ids = inbound_ids_to_json(attach)
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row

    async def set_display_name(
        self, telegram_id: int, display_name: str
    ) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        row.display_name = display_name
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_active(self, telegram_id: int, active: bool) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        row.is_active = active
        await self.session.commit()
        return row

    async def set_panel_id(self, telegram_id: int, panel_id: int) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        count = await self.client_count(telegram_id)
        if count > 0:
            raise ValueError("ریسلر دارای سرویس است؛ تغییر پنل مجاز نیست.")
        row.panel_id = panel_id
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_max_clients(
        self, telegram_id: int, max_clients: int | None
    ) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        row.max_clients = max_clients
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row

    async def active_bytes(self, telegram_id: int) -> int:
        result = await self.session.scalar(
            select(func.coalesce(func.sum(ClientRecord.allocated_bytes), 0)).where(
                ClientRecord.reseller_tg_id == telegram_id
            )
        )
        return int(result or 0)

    async def used_bytes(self, telegram_id: int) -> int:
        """Sum of active service allocations (alias for active_bytes)."""
        return await self.active_bytes(telegram_id)

    async def add_lifetime_allocated(self, telegram_id: int, delta: int) -> None:
        row = await self.get(telegram_id)
        if not row:
            raise ValueError("ریسلر یافت نشد.")
        row.lifetime_allocated_bytes += delta
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)

    async def subtract_lifetime_allocated(
        self, telegram_id: int, delta: int
    ) -> None:
        row = await self.get(telegram_id)
        if not row:
            raise ValueError("ریسلر یافت نشد.")
        row.lifetime_allocated_bytes = max(
            0, int(row.lifetime_allocated_bytes or 0) - delta
        )
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)

    async def reset_lifetime_to_active(self, telegram_id: int) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        row.lifetime_allocated_bytes = await self.active_bytes(telegram_id)
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row

    async def add_quota_bytes(self, telegram_id: int, delta: int) -> Reseller | None:
        row = await self.get(telegram_id)
        if not row:
            return None
        row.quota_bytes += delta
        await self.session.commit()
        await self.session.refresh(row)
        await self._sync_primary_panel_assignment(row)
        return row

    async def client_count(self, telegram_id: int) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(ClientRecord).where(
                ClientRecord.reseller_tg_id == telegram_id
            )
        )
        return int(result or 0)

    async def client_count_on_panel(
        self, telegram_id: int, panel_id: int
    ) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(ClientRecord)
            .where(
                ClientRecord.reseller_tg_id == telegram_id,
                ClientRecord.panel_id == panel_id,
            )
        )
        return int(result or 0)

    async def active_bytes_on_panel(
        self, telegram_id: int, panel_id: int
    ) -> int:
        result = await self.session.scalar(
            select(func.coalesce(func.sum(ClientRecord.allocated_bytes), 0)).where(
                ClientRecord.reseller_tg_id == telegram_id,
                ClientRecord.panel_id == panel_id,
            )
        )
        return int(result or 0)

    async def delete(self, telegram_id: int) -> bool:
        row = await self.get(telegram_id)
        if not row:
            return False
        count = await self.client_count(telegram_id)
        if count > 0:
            raise ValueError(
                "ریسلر دارای سرویس است؛ ابتدا همه سرویس‌ها را حذف کنید."
            )
        await self.session.execute(
            delete(UsageAlertSent).where(
                UsageAlertSent.reseller_tg_id == telegram_id
            )
        )
        await self.session.delete(row)
        await self.session.commit()
        return True

    async def sync_legacy_from_primary_panel(
        self, telegram_id: int, panel_repo: "ResellerPanelRepository"
    ) -> None:
        """Keep resellers.* in sync with default panel assignment (compat)."""
        row = await self.get(telegram_id)
        if not row:
            return
        primary = await panel_repo.get(telegram_id, row.panel_id)
        if not primary:
            return
        row.quota_bytes = primary.quota_bytes
        row.lifetime_allocated_bytes = primary.lifetime_allocated_bytes
        row.allowed_inbound_ids = primary.allowed_inbound_ids
        row.attach_inbound_ids = primary.attach_inbound_ids
        row.max_clients = primary.max_clients
        await self.session.commit()
        await self.session.refresh(row)


class ResellerPanelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, reseller_tg_id: int, panel_id: int
    ) -> ResellerPanel | None:
        return await self.session.get(
            ResellerPanel, (reseller_tg_id, panel_id)
        )

    async def list_for_reseller(
        self, reseller_tg_id: int, *, active_only: bool = False
    ) -> list[ResellerPanel]:
        q = select(ResellerPanel).where(
            ResellerPanel.reseller_tg_id == reseller_tg_id
        )
        if active_only:
            q = q.where(ResellerPanel.is_active.is_(True))
        result = await self.session.scalars(
            q.order_by(ResellerPanel.panel_id)
        )
        return list(result.all())

    async def list_active_panel_ids(self, reseller_tg_id: int) -> list[int]:
        rows = await self.list_for_reseller(reseller_tg_id, active_only=True)
        return [r.panel_id for r in rows]

    async def add(
        self,
        reseller_tg_id: int,
        panel_id: int,
        quota_bytes: int,
        allowed_inbound_ids: list[int],
        *,
        attach_inbound_ids: list[int] | None = None,
        max_clients: int | None = None,
        is_active: bool = True,
    ) -> ResellerPanel:
        existing = await self.get(reseller_tg_id, panel_id)
        if existing:
            raise ValueError("این پنل قبلاً به ریسلر اختصاص داده شده.")
        if not allowed_inbound_ids:
            raise ValueError("لیست اینباندهای مجاز نمی‌تواند خالی باشد.")
        attach = attach_inbound_ids if attach_inbound_ids else allowed_inbound_ids
        validate_inbound_subset(allowed_inbound_ids, attach)
        row = ResellerPanel(
            reseller_tg_id=reseller_tg_id,
            panel_id=panel_id,
            quota_bytes=quota_bytes,
            lifetime_allocated_bytes=0,
            allowed_inbound_ids=inbound_ids_to_json(allowed_inbound_ids),
            attach_inbound_ids=inbound_ids_to_json(attach),
            max_clients=max_clients,
            is_active=is_active,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_quota_bytes(
        self, reseller_tg_id: int, panel_id: int, quota_bytes: int
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        row.quota_bytes = quota_bytes
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def add_quota_bytes(
        self, reseller_tg_id: int, panel_id: int, delta: int
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        row.quota_bytes += delta
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def add_lifetime_allocated(
        self, reseller_tg_id: int, panel_id: int, delta: int
    ) -> None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            raise ValueError("تخصیص پنل یافت نشد.")
        row.lifetime_allocated_bytes += delta
        await self.session.commit()
        await self.session.refresh(row)

    async def subtract_lifetime_allocated(
        self, reseller_tg_id: int, panel_id: int, delta: int
    ) -> None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            raise ValueError("تخصیص پنل یافت نشد.")
        row.lifetime_allocated_bytes = max(
            0, int(row.lifetime_allocated_bytes or 0) - delta
        )
        await self.session.commit()
        await self.session.refresh(row)

    async def reset_lifetime_to_active(
        self, reseller_tg_id: int, panel_id: int, active_bytes: int
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        row.lifetime_allocated_bytes = active_bytes
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_allowed_inbound_ids(
        self, reseller_tg_id: int, panel_id: int, allowed: list[int]
    ) -> tuple[ResellerPanel | None, bool]:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None, False
        if not allowed:
            raise ValueError("لیست اینباندهای مجاز نمی‌تواند خالی باشد.")
        old_attach = resolve_attach_inbound_ids_for_assignment(row)
        row.allowed_inbound_ids = inbound_ids_to_json(allowed)
        row.attach_inbound_ids = inbound_ids_to_json(allowed)
        was_trimmed = set(old_attach) != set(allowed)
        await self.session.commit()
        await self.session.refresh(row)
        return row, was_trimmed

    async def set_attach_inbound_ids(
        self, reseller_tg_id: int, panel_id: int, attach: list[int]
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        allowed = inbound_ids_from_json(row.allowed_inbound_ids)
        validate_inbound_subset(allowed, attach)
        row.attach_inbound_ids = inbound_ids_to_json(attach)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_max_clients(
        self, reseller_tg_id: int, panel_id: int, max_clients: int | None
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        row.max_clients = max_clients
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_active(
        self, reseller_tg_id: int, panel_id: int, active: bool
    ) -> ResellerPanel | None:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return None
        row.is_active = active
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, reseller_tg_id: int, panel_id: int) -> bool:
        row = await self.get(reseller_tg_id, panel_id)
        if not row:
            return False
        reseller_repo = ResellerRepository(self.session)
        if await reseller_repo.client_count_on_panel(reseller_tg_id, panel_id) > 0:
            raise ValueError("ریسلر روی این پنل سرویس دارد؛ حذف تخصیص مجاز نیست.")
        assignments = await self.list_for_reseller(reseller_tg_id)
        if len(assignments) <= 1:
            raise ValueError("حداقل یک پنل باید برای ریسلر باقی بماند.")
        await self.session.delete(row)
        await self.session.commit()
        return True

    async def assignment_count_on_panel(self, panel_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(ResellerPanel)
            .where(ResellerPanel.panel_id == panel_id)
        )
        return int(result or 0)


class ClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(
        self, email: str, *, panel_id: int | None = None
    ) -> ClientRecord | None:
        q = select(ClientRecord).where(ClientRecord.email == email)
        if panel_id is not None:
            q = q.where(ClientRecord.panel_id == panel_id)
        return await self.session.scalar(q)

    async def get_for_reseller_email(
        self, reseller_tg_id: int, email: str
    ) -> ClientRecord | None:
        return await self.session.scalar(
            select(ClientRecord).where(
                ClientRecord.reseller_tg_id == reseller_tg_id,
                ClientRecord.email == email,
            )
        )

    async def list_for_reseller_on_panels(
        self, reseller_tg_id: int, panel_ids: set[int] | list[int]
    ) -> list[ClientRecord]:
        if not panel_ids:
            return []
        ids = list(panel_ids)
        result = await self.session.scalars(
            select(ClientRecord)
            .where(
                ClientRecord.reseller_tg_id == reseller_tg_id,
                ClientRecord.panel_id.in_(ids),
            )
            .order_by(ClientRecord.created_at.desc())
        )
        return list(result.all())

    async def email_exists(self, email: str, *, panel_id: int) -> bool:
        row = await self.get_by_email(email, panel_id=panel_id)
        return row is not None

    async def list_for_reseller(self, reseller_tg_id: int) -> list[ClientRecord]:
        result = await self.session.scalars(
            select(ClientRecord)
            .where(ClientRecord.reseller_tg_id == reseller_tg_id)
            .order_by(ClientRecord.created_at.desc())
        )
        return list(result.all())

    async def add(
        self,
        reseller_tg_id: int,
        panel_id: int,
        email: str,
        inbound_ids: list[int],
        allocated_bytes: int,
        expiry_time: int = 0,
        sub_id: str | None = None,
    ) -> ClientRecord:
        row = ClientRecord(
            reseller_tg_id=reseller_tg_id,
            panel_id=panel_id,
            email=email,
            sub_id=sub_id,
            inbound_ids=inbound_ids_to_json(inbound_ids),
            allocated_bytes=allocated_bytes,
            expiry_time=expiry_time,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_sub_id(self, record: ClientRecord, sub_id: str) -> ClientRecord:
        record.sub_id = sub_id
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def set_expiry_time(
        self, record: ClientRecord, expiry_ms: int
    ) -> ClientRecord:
        record.expiry_time = expiry_ms
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def add_allocated_bytes(
        self, record: ClientRecord, delta: int
    ) -> ClientRecord:
        record.allocated_bytes += delta
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def subtract_allocated_bytes(
        self, record: ClientRecord, delta: int
    ) -> ClientRecord:
        record.allocated_bytes = max(0, int(record.allocated_bytes or 0) - delta)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def delete(self, record: ClientRecord) -> None:
        await self.session.delete(record)
        await self.session.commit()

    async def list_all(self) -> list[ClientRecord]:
        result = await self.session.scalars(
            select(ClientRecord).order_by(ClientRecord.reseller_tg_id)
        )
        return list(result.all())


class UsageAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _client_key(client_email: str | None) -> str:
        return (client_email or "").strip()

    async def get_sent_thresholds(
        self,
        reseller_tg_id: int,
        alert_kind: str,
        *,
        client_email: str | None,
    ) -> set[int]:
        key = self._client_key(client_email)
        result = await self.session.scalars(
            select(UsageAlertSent.threshold_percent).where(
                UsageAlertSent.reseller_tg_id == reseller_tg_id,
                UsageAlertSent.alert_kind == alert_kind,
                UsageAlertSent.client_email == key,
            )
        )
        return {int(x) for x in result.all()}

    async def mark_sent(
        self,
        reseller_tg_id: int,
        alert_kind: str,
        threshold_percent: int,
        *,
        client_email: str | None,
    ) -> None:
        key = self._client_key(client_email)
        existing = await self.session.scalar(
            select(UsageAlertSent).where(
                UsageAlertSent.reseller_tg_id == reseller_tg_id,
                UsageAlertSent.alert_kind == alert_kind,
                UsageAlertSent.client_email == key,
                UsageAlertSent.threshold_percent == threshold_percent,
            )
        )
        if existing:
            return
        self.session.add(
            UsageAlertSent(
                reseller_tg_id=reseller_tg_id,
                alert_kind=alert_kind,
                client_email=key,
                threshold_percent=threshold_percent,
            )
        )
        await self.session.commit()

    async def clear(
        self,
        reseller_tg_id: int,
        alert_kind: str,
        *,
        client_email: str | None,
    ) -> None:
        key = self._client_key(client_email)
        rows = await self.session.scalars(
            select(UsageAlertSent).where(
                UsageAlertSent.reseller_tg_id == reseller_tg_id,
                UsageAlertSent.alert_kind == alert_kind,
                UsageAlertSent.client_email == key,
            )
        )
        for row in rows.all():
            await self.session.delete(row)
        await self.session.commit()


class PanelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, panel_id: int) -> Panel | None:
        return await self.session.get(Panel, panel_id)

    async def list_all(self) -> list[Panel]:
        result = await self.session.scalars(
            select(Panel).order_by(Panel.id)
        )
        return list(result.all())

    async def list_active(self) -> list[Panel]:
        result = await self.session.scalars(
            select(Panel).where(Panel.is_active.is_(True)).order_by(Panel.id)
        )
        return list(result.all())

    async def create(
        self,
        name: str,
        base_url: str,
        *,
        api_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        sub_public_url: str | None = None,
        verify_ssl: bool = True,
        auto_vision_flow: bool = True,
        auto_reseller_group: bool = True,
    ) -> Panel:
        name = name.strip()
        if not name:
            raise ValueError("نام پنل نمی‌تواند خالی باشد.")
        if not api_token and not (username and password):
            raise ValueError("توکن API یا نام کاربری/رمز لازم است.")
        normalized_base = normalize_http_url(base_url)
        normalized_sub = None
        if sub_public_url and str(sub_public_url).strip():
            normalized_sub = normalize_sub_public_url(str(sub_public_url))
        row = Panel(
            name=name,
            base_url=normalized_base,
            api_token=api_token,
            username=username,
            password=password,
            sub_public_url=normalized_sub,
            verify_ssl=verify_ssl,
            auto_vision_flow=auto_vision_flow,
            auto_reseller_group=auto_reseller_group,
            is_active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_active(self, panel_id: int, active: bool) -> Panel | None:
        row = await self.get(panel_id)
        if not row:
            return None
        row.is_active = active
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_name(self, panel_id: int, name: str) -> Panel | None:
        row = await self.get(panel_id)
        if not row:
            return None
        name = name.strip()
        if not name:
            raise ValueError("نام پنل نمی‌تواند خالی باشد.")
        row.name = name
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_base_url(self, panel_id: int, base_url: str) -> Panel | None:
        row = await self.get(panel_id)
        if not row:
            return None
        row.base_url = normalize_http_url(base_url)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_api_token(self, panel_id: int, api_token: str) -> Panel | None:
        row = await self.get(panel_id)
        if not row:
            return None
        token = api_token.strip()
        if not token:
            raise ValueError("توکن API نمی‌تواند خالی باشد.")
        row.api_token = token
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_sub_public_url(
        self, panel_id: int, sub_public_url: str | None
    ) -> Panel | None:
        row = await self.get(panel_id)
        if not row:
            return None
        if sub_public_url is None or not str(sub_public_url).strip():
            row.sub_public_url = None
        else:
            row.sub_public_url = normalize_sub_public_url(str(sub_public_url))
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def reseller_count(self, panel_id: int) -> int:
        rp = ResellerPanelRepository(self.session)
        count = await rp.assignment_count_on_panel(panel_id)
        if count > 0:
            return count
        result = await self.session.scalar(
            select(func.count())
            .select_from(Reseller)
            .where(Reseller.panel_id == panel_id)
        )
        return int(result or 0)

    async def delete(self, panel_id: int) -> bool:
        if panel_id == 1:
            raise ValueError("پنل پیش‌فرض قابل حذف نیست.")
        rp = ResellerPanelRepository(self.session)
        if await rp.assignment_count_on_panel(panel_id) > 0:
            raise ValueError("این پنل ریسلر دارد؛ ابتدا تخصیص‌ها را حذف کنید.")
        if await self.reseller_count(panel_id) > 0:
            raise ValueError("این پنل ریسلر دارد؛ ابتدا ریسلرها را منتقل یا حذف کنید.")
        row = await self.get(panel_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True


class ServiceTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[ServiceTemplate]:
        result = await self.session.scalars(
            select(ServiceTemplate)
            .where(ServiceTemplate.is_active.is_(True))
            .order_by(ServiceTemplate.sort_order, ServiceTemplate.id)
        )
        return list(result.all())

    async def get_active(self, template_id: int) -> ServiceTemplate | None:
        row = await self.session.get(ServiceTemplate, template_id)
        if row is None or not row.is_active:
            return None
        return row

    async def create(
        self,
        name: str,
        volume_gb: float,
        expiry_days: int,
        *,
        sort_order: int | None = None,
    ) -> ServiceTemplate:
        name = normalize_template_name(name)
        validate_template_params(volume_gb, expiry_days)
        if sort_order is None:
            max_sort = await self.session.scalar(
                select(func.max(ServiceTemplate.sort_order))
            )
            sort_order = (max_sort or 0) + 1
        row = ServiceTemplate(
            name=name,
            volume_gb=volume_gb,
            expiry_days=expiry_days,
            sort_order=sort_order,
            is_active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, template_id: int) -> bool:
        row = await self.session.get(ServiceTemplate, template_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True

    async def list_all(self) -> list[ServiceTemplate]:
        result = await self.session.scalars(
            select(ServiceTemplate).order_by(
                ServiceTemplate.sort_order, ServiceTemplate.id
            )
        )
        return list(result.all())
