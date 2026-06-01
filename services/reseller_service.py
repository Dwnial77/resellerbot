from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClientRecord, Reseller
from db.repository import (
    ClientRepository,
    ResellerRepository,
    UsageAlertRepository,
    inbound_ids_from_json,
    resolve_attach_inbound_ids,
)
from services.usage_alerts import CLIENT_TRAFFIC
from services.quota import QuotaExceeded, QuotaService
from agent_debug import agent_log
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
        self.client_repo = ClientRepository(session)
        self.quota = QuotaService(self.reseller_repo)
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
    ) -> tuple[ClientRecord, ClientDelivery]:
        ids = inbound_ids or resolve_attach_inbound_ids(reseller)
        # #region agent log
        agent_log(
            "F",
            "reseller_service.py:create_service",
            "inbound lists",
            {
                "allowed": inbound_ids_from_json(reseller.allowed_inbound_ids),
                "attach_raw": reseller.attach_inbound_ids,
                "attach_resolved": ids,
            },
            run_id="post-fix",
        )
        # #endregion
        allocated = await self.quota.validate_create(reseller, volume_gb, ids)

        email = build_client_email(reseller, client_suffix)
        if await self.client_repo.email_exists(email, panel_id=reseller.panel_id):
            raise XuiError("این نام سرویس قبلاً استفاده شده.")
        # #region agent log
        agent_log(
            "B",
            "reseller_service.py:create_service",
            "panel get_client check",
            {"inbound_ids": ids},
        )
        # #endregion
        existing_panel = await self.xui.get_client(email)
        # #region agent log
        agent_log(
            "B",
            "reseller_service.py:create_service",
            "panel get_client result",
            {"exists_on_panel": existing_panel is not None},
        )
        # #endregion
        if existing_panel is not None:
            raise XuiError("این نام سرویس در پنل وجود دارد.")
        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int((time.time() + expiry_days * 86400) * 1000)

        record = await self.client_repo.add(
            reseller_tg_id=reseller.telegram_id,
            panel_id=reseller.panel_id,
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
            # #region agent log
            agent_log(
                "D",
                "reseller_service.py:create_service",
                "fetching delivery",
                {},
            )
            # #endregion
            delivery = await self.xui.get_client_delivery(
                email, sub_id, total_bytes=allocated
            )
            # #region agent log
            agent_log(
                "D",
                "reseller_service.py:create_service",
                "create_service ok",
                {
                    "vless_count": len(delivery.vless_links),
                    "sub_count": len(delivery.subscription_links),
                },
            )
            # #endregion
        except (XuiError, Exception) as e:
            # #region agent log
            agent_log(
                "E",
                "reseller_service.py:create_service",
                "create_service failed",
                {"error_type": type(e).__name__, "error": str(e)[:300]},
            )
            # #endregion
            await self.client_repo.delete(record)
            raise XuiError(str(e) or "خطای ناشناخته پنل") from e

        return record, delivery

    async def delete_service(
        self, reseller: Reseller, email: str
    ) -> None:
        record = await self.client_repo.get_by_email(
            email, panel_id=reseller.panel_id
        )
        if not record or record.reseller_tg_id != reseller.telegram_id:
            raise XuiError("سرویس یافت نشد یا متعلق به شما نیست.")
        try:
            await self.xui.delete_client(email)
        except XuiError:
            pass
        await UsageAlertRepository(self.client_repo.session).clear(
            reseller.telegram_id, CLIENT_TRAFFIC, client_email=email
        )
        await self.client_repo.delete(record)

    async def get_traffic(self, reseller: Reseller, email: str) -> dict:
        record = await self.client_repo.get_by_email(
            email, panel_id=reseller.panel_id
        )
        if not record or record.reseller_tg_id != reseller.telegram_id:
            raise XuiError("سرویس یافت نشد.")
        return await self.xui.get_traffic(email)

    async def set_service_enabled(
        self, reseller: Reseller, email: str, enabled: bool
    ) -> None:
        record = await self.client_repo.get_by_email(
            email, panel_id=reseller.panel_id
        )
        if not record or record.reseller_tg_id != reseller.telegram_id:
            raise XuiError("سرویس یافت نشد یا متعلق به شما نیست.")
        await self.xui.set_client_enabled(email, enabled)

    async def _get_owned_record(self, reseller: Reseller, email: str) -> ClientRecord:
        record = await self.client_repo.get_by_email(
            email, panel_id=reseller.panel_id
        )
        if not record or record.reseller_tg_id != reseller.telegram_id:
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
        record = await self.client_repo.get_by_email(
            email, panel_id=reseller.panel_id
        )
        if not record or record.reseller_tg_id != reseller.telegram_id:
            raise XuiError("سرویس یافت نشد.")
        return await self.xui.get_client_delivery(
            email, record.sub_id, total_bytes=record.allocated_bytes
        )

    async def get_links(self, reseller: Reseller, email: str) -> list[str]:
        delivery = await self.get_delivery(reseller, email)
        return delivery.vless_links + delivery.subscription_links
