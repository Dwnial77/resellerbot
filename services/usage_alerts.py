"""Usage threshold checks and Telegram alert messages (80% / 90%)."""

from __future__ import annotations

from dataclasses import dataclass
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from bot.utils.format_traffic import format_bytes, normalize_traffic_data
from db.models import ClientRecord, Reseller
from db.repository import (
    ClientRepository,
    ResellerRepository,
    UsageAlertRepository,
)
from services.panel_registry import PanelNotFoundError, PanelRegistry
from services.quota import QuotaService
from xui.client import XuiError

RESET_BELOW_PERCENT = 75

RESELLER_QUOTA = "reseller_quota"
CLIENT_TRAFFIC = "client_traffic"


@dataclass
class AlertToSend:
    reseller_tg_id: int
    alert_kind: str
    threshold_percent: int
    message: str
    client_email: str | None = None


def pending_thresholds(percent: int, already_sent: set[int]) -> list[int]:
    if percent < RESET_BELOW_PERCENT:
        return []
    out: list[int] = []
    if percent >= 80 and 80 not in already_sent:
        out.append(80)
    if percent >= 90 and 90 not in already_sent:
        out.append(90)
    return out


def usage_percent(used: int, total: int) -> int | None:
    if total <= 0:
        return None
    return min(100, int(round(used * 100 / total)))


class UsageAlertService:
    def __init__(
        self,
        session: AsyncSession,
        registry: PanelRegistry,
    ) -> None:
        self.session = session
        self.registry = registry
        self.reseller_repo = ResellerRepository(session)
        self.client_repo = ClientRepository(session)
        self.alert_repo = UsageAlertRepository(session)
        self.quota = QuotaService(self.reseller_repo)

    async def collect_pending_alerts(self) -> list[AlertToSend]:
        pending: list[AlertToSend] = []
        resellers = await self.reseller_repo.list_all()
        for reseller in resellers:
            if not reseller.is_active:
                continue
            pending.extend(await self._check_reseller_quota(reseller))
            pending.extend(await self._check_clients(reseller))
        return pending

    async def _check_reseller_quota(self, reseller: Reseller) -> list[AlertToSend]:
        if reseller.quota_bytes <= 0:
            return []
        st = await self.quota.status(reseller)
        percent = usage_percent(st.used_bytes, st.quota_bytes)
        if percent is None:
            return []
        sent = await self.alert_repo.get_sent_thresholds(
            reseller.telegram_id, RESELLER_QUOTA, client_email=None
        )
        if percent < RESET_BELOW_PERCENT:
            await self.alert_repo.clear(
                reseller.telegram_id, RESELLER_QUOTA, client_email=None
            )
            return []
        alerts: list[AlertToSend] = []
        for threshold in pending_thresholds(percent, sent):
            alerts.append(
                AlertToSend(
                    reseller_tg_id=reseller.telegram_id,
                    alert_kind=RESELLER_QUOTA,
                    threshold_percent=threshold,
                    message=t.USAGE_ALERT_RESELLER.format(
                        threshold=threshold,
                        used_gb=st.used_gb,
                        quota_gb=st.quota_gb,
                        percent=percent,
                    ),
                )
            )
        return alerts

    async def _check_clients(self, reseller: Reseller) -> list[AlertToSend]:
        alerts: list[AlertToSend] = []
        clients = await self.client_repo.list_for_reseller(reseller.telegram_id)
        for record in clients:
            alerts.extend(await self._check_one_client(reseller, record))
        return alerts

    async def _check_one_client(
        self, reseller: Reseller, record: ClientRecord
    ) -> list[AlertToSend]:
        try:
            xui = self.registry.get_client(reseller.panel_id)
        except PanelNotFoundError:
            return []
        try:
            raw = await xui.get_traffic(record.email)
        except XuiError:
            return []
        row = normalize_traffic_data(raw)
        up = int(row.get("up") or 0)
        down = int(row.get("down") or 0)
        used = up + down
        total = int(row.get("total") or 0)
        if total <= 0:
            total = record.allocated_bytes
        percent = usage_percent(used, total)
        if percent is None:
            return []
        sent = await self.alert_repo.get_sent_thresholds(
            reseller.telegram_id, CLIENT_TRAFFIC, client_email=record.email
        )
        if percent < RESET_BELOW_PERCENT:
            await self.alert_repo.clear(
                reseller.telegram_id, CLIENT_TRAFFIC, client_email=record.email
            )
            return []
        alerts: list[AlertToSend] = []
        for threshold in pending_thresholds(percent, sent):
            alerts.append(
                AlertToSend(
                    reseller_tg_id=reseller.telegram_id,
                    alert_kind=CLIENT_TRAFFIC,
                    threshold_percent=threshold,
                    client_email=record.email,
                    message=t.USAGE_ALERT_CLIENT.format(
                        threshold=threshold,
                        email=record.email,
                        used=format_bytes(used),
                        total=format_bytes(total),
                        percent=percent,
                    ),
                )
            )
        return alerts

    async def mark_sent(self, alert: AlertToSend) -> None:
        await self.alert_repo.mark_sent(
            alert.reseller_tg_id,
            alert.alert_kind,
            alert.threshold_percent,
            client_email=alert.client_email,
        )


async def run_usage_alert_cycle(
    bot: Bot, registry: PanelRegistry, session: AsyncSession
) -> int:
    svc = UsageAlertService(session, registry)
    pending = await svc.collect_pending_alerts()
    sent_count = 0
    for alert in pending:
        try:
            await bot.send_message(alert.reseller_tg_id, alert.message)
            await svc.mark_sent(alert)
            sent_count += 1
        except Exception:
            continue
    return sent_count
