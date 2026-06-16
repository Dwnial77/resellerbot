from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.utils.format_traffic import client_traffic_used_bytes
from db.models import ClientRecord, Reseller
from db.repository import (
    ClientRepository,
    ResellerPanelRepository,
    ResellerRepository,
    UsageAlertRepository,
    resolve_attach_inbound_ids_for_assignment,
)
from services.usage_alerts import CLIENT_TRAFFIC
from services.quota import QuotaExceeded, QuotaService
from bot.utils.edit_service import (
    InvalidEditInputError,
    validate_comment,
    validate_limit_ip,
)
from services.reseller_labels import build_client_email, panel_group_name
from xui.client import (
    ClientDelivery,
    XuiClient,
    XuiError,
    gb_to_bytes,
    read_comment,
    read_limit_ip,
    resolve_expiry_after_add_days,
)


@dataclass
class DeleteServiceResult:
    refunded_bytes: int


@dataclass
class AddTrafficResult:
    added_bytes: int
    new_total_bytes: int
    remaining_bytes: int


@dataclass
class RemoveTrafficResult:
    removed_bytes: int
    new_total_bytes: int
    remaining_bytes: int


def is_quota_refund_eligible(
    used_bytes: int, *, max_traffic_gb: float | None = None
) -> bool:
    threshold_gb = (
        max_traffic_gb
        if max_traffic_gb is not None
        else get_settings().quota_refund_max_traffic_gb
    )
    return used_bytes < gb_to_bytes(threshold_gb)


class ResellerService:
    def __init__(
        self,
        session: AsyncSession,
        xui: XuiClient | None,
    ) -> None:
        if xui is None:
            raise XuiError(
                "پنل اختصاصی شما در دسترس نیست. با ادمین تماس بگیرید."
            )
        self.reseller_repo = ResellerRepository(session)
        self.panel_repo = ResellerPanelRepository(session)
        self.client_repo = ClientRepository(session)
        self.quota = QuotaService(self.reseller_repo, self.panel_repo)
        self.xui = xui

    async def get_reseller(self, telegram_id: int) -> Reseller | None:
        return await self.reseller_repo.get(telegram_id)

    async def create_service(
        self,
        reseller: Reseller,
        volume_gb: float,
        expiry_days: int = 0,
        inbound_ids: list[int] | None = None,
        *,
        client_suffix: str,
        panel_id: int,
    ) -> tuple[ClientRecord, ClientDelivery]:
        assignment = await self.panel_repo.get(reseller.telegram_id, panel_id)
        if not assignment:
            raise XuiError("این پنل به حساب شما اختصاص داده نشده.")
        ids = inbound_ids or resolve_attach_inbound_ids_for_assignment(assignment)
        allocated = await self.quota.validate_create(
            reseller, panel_id, volume_gb, ids
        )

        email = build_client_email(reseller, client_suffix)
        if await self.client_repo.email_exists(email, panel_id=panel_id):
            raise XuiError("این نام سرویس قبلاً استفاده شده.")
        existing_panel = await self.xui.get_client(email)
        if existing_panel is not None:
            raise XuiError("این نام سرویس در پنل وجود دارد.")
        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int((time.time() + expiry_days * 86400) * 1000)

        record = await self.client_repo.add(
            reseller_tg_id=reseller.telegram_id,
            panel_id=panel_id,
            email=email,
            inbound_ids=ids,
            allocated_bytes=allocated,
            expiry_time=expiry_ms,
        )

        panel_group = ""
        if self.xui.auto_reseller_group:
            panel_group = panel_group_name(reseller)

        try:
            _, sub_id = await self.xui.create_client(
                email=email,
                volume_gb=volume_gb,
                inbound_ids=ids,
                expiry_days=expiry_days,
                group=panel_group,
            )
            record = await self.client_repo.set_sub_id(record, sub_id)
            delivery = await self.xui.get_client_delivery(
                email, sub_id, total_bytes=allocated
            )
        except (XuiError, Exception) as e:
            await self.client_repo.delete(record)
            raise XuiError(str(e) or "خطای ناشناخته پنل") from e

        await self.reseller_repo.add_lifetime_allocated(
            reseller.telegram_id, allocated
        )
        return record, delivery

    async def delete_service(
        self, reseller: Reseller, email: str
    ) -> DeleteServiceResult:
        record = await self._get_owned_record(reseller, email)
        refund = 0
        try:
            traffic = await self.xui.get_traffic(email)
            if is_quota_refund_eligible(client_traffic_used_bytes(traffic)):
                refund = record.allocated_bytes
        except XuiError:
            pass
        try:
            await self.xui.delete_client(email)
        except XuiError:
            pass
        await UsageAlertRepository(self.client_repo.session).clear(
            reseller.telegram_id, CLIENT_TRAFFIC, client_email=email
        )
        await self.client_repo.delete(record)
        if refund > 0:
            await self.reseller_repo.subtract_lifetime_allocated(
                reseller.telegram_id, refund
            )
        return DeleteServiceResult(refunded_bytes=refund)

    async def get_traffic(self, reseller: Reseller, email: str) -> dict:
        await self._get_owned_record(reseller, email)
        return await self.xui.get_traffic(email)

    async def set_service_enabled(
        self, reseller: Reseller, email: str, enabled: bool
    ) -> None:
        await self._get_owned_record(reseller, email)
        await self.xui.set_client_enabled(email, enabled)

    async def _get_owned_record(self, reseller: Reseller, email: str) -> ClientRecord:
        record = await self.client_repo.get_for_reseller_email(
            reseller.telegram_id, email
        )
        if not record:
            raise XuiError("سرویس یافت نشد یا متعلق به شما نیست.")
        return record

    async def _current_expiry_ms(self, email: str, record: ClientRecord) -> int:
        panel = await self.xui.get_client(email)
        if panel:
            raw = panel.get("expiryTime", panel.get("expiry_time", 0))
            try:
                return int(raw or 0)
            except (TypeError, ValueError):
                pass
        return int(record.expiry_time or 0)

    async def update_service_expiry(
        self,
        reseller: Reseller,
        email: str,
        *,
        add_days: int | None = None,
        expiry_ms: int | None = None,
    ) -> int:
        record = await self._get_owned_record(reseller, email)
        if add_days is not None:
            if add_days < 1:
                raise XuiError("تعداد روز باید حداقل ۱ باشد.")
            current = await self._current_expiry_ms(email, record)
            new_ms = resolve_expiry_after_add_days(current, add_days)
            await self.xui.add_client_expiry_days(email, add_days)
            await self.client_repo.set_expiry_time(record, new_ms)
            return new_ms
        if expiry_ms is not None:
            await self.xui.set_client_expiry_ms(email, expiry_ms)
            await self.client_repo.set_expiry_time(record, expiry_ms)
            return expiry_ms
        raise XuiError("پارامتر انقضا مشخص نشده.")

    async def get_client_panel_fields(
        self, reseller: Reseller, email: str
    ) -> tuple[int, str]:
        await self._get_owned_record(reseller, email)
        client = await self.xui.get_client(email)
        if not client:
            raise XuiError("کلاینت در پنل یافت نشد.")
        return read_limit_ip(client), read_comment(client)

    async def reset_service_traffic(self, reseller: Reseller, email: str) -> None:
        await self._get_owned_record(reseller, email)
        await self.xui.reset_client_traffic(email)

    async def add_service_traffic(
        self, reseller: Reseller, email: str, volume_gb: float
    ) -> AddTrafficResult:
        record = await self._get_owned_record(reseller, email)
        panel_id = record.panel_id
        try:
            allocated = await self.quota.validate_add_traffic(
                reseller, panel_id, volume_gb
            )
        except QuotaExceeded as e:
            raise XuiError(str(e)) from e
        await self.xui.add_client_traffic_bytes(email, allocated)
        record = await self.client_repo.add_allocated_bytes(record, allocated)
        await self.reseller_repo.add_lifetime_allocated(
            reseller.telegram_id, allocated
        )
        st = await self.quota.global_status(reseller)
        return AddTrafficResult(
            added_bytes=allocated,
            new_total_bytes=record.allocated_bytes,
            remaining_bytes=st.remaining_bytes,
        )

    async def remove_service_traffic(
        self, reseller: Reseller, email: str, volume_gb: float
    ) -> RemoveTrafficResult:
        record = await self._get_owned_record(reseller, email)
        panel_id = record.panel_id
        try:
            traffic = await self.xui.get_traffic(email)
            used_bytes = client_traffic_used_bytes(traffic)
            removed = self.quota.validate_remove_traffic(
                reseller,
                volume_gb,
                current_allocated_bytes=record.allocated_bytes,
                used_bytes=used_bytes,
            )
        except QuotaExceeded as e:
            raise XuiError(str(e)) from e
        await self.xui.subtract_client_traffic_bytes(email, removed)
        record = await self.client_repo.subtract_allocated_bytes(record, removed)
        await self.reseller_repo.subtract_lifetime_allocated(
            reseller.telegram_id, removed
        )
        st = await self.quota.global_status(reseller)
        return RemoveTrafficResult(
            removed_bytes=removed,
            new_total_bytes=record.allocated_bytes,
            remaining_bytes=st.remaining_bytes,
        )

    async def update_service_limit_ip(
        self, reseller: Reseller, email: str, limit_ip: int
    ) -> int:
        await self._get_owned_record(reseller, email)
        try:
            validated = validate_limit_ip(limit_ip)
        except InvalidEditInputError as e:
            raise XuiError(str(e)) from e
        await self.xui.update_client_fields(email, limit_ip=validated)
        return validated

    async def update_service_comment(
        self, reseller: Reseller, email: str, comment: str
    ) -> str:
        await self._get_owned_record(reseller, email)
        try:
            validated = validate_comment(comment)
        except InvalidEditInputError as e:
            raise XuiError(str(e)) from e
        await self.xui.update_client_fields(email, comment=validated)
        return validated

    async def get_delivery(self, reseller: Reseller, email: str) -> ClientDelivery:
        record = await self._get_owned_record(reseller, email)
        return await self.xui.get_client_delivery(
            email, record.sub_id, total_bytes=record.allocated_bytes
        )

    async def get_links(self, reseller: Reseller, email: str) -> list[str]:
        delivery = await self.get_delivery(reseller, email)
        return delivery.vless_links + delivery.subscription_links
