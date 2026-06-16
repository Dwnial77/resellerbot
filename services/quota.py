import json
from dataclasses import dataclass

from db.models import Reseller, ResellerPanel
from db.repository import ResellerPanelRepository, ResellerRepository
from services.client_volume import validate_client_volume_gb
from xui.client import bytes_to_gb, gb_to_bytes


@dataclass
class QuotaStatus:
    quota_bytes: int
    active_bytes: int
    lifetime_bytes: int
    remaining_bytes: int
    client_count: int
    max_clients: int | None
    panel_id: int | None = None

    @property
    def used_bytes(self) -> int:
        return self.lifetime_bytes

    @property
    def quota_gb(self) -> float:
        return bytes_to_gb(self.quota_bytes)

    @property
    def active_gb(self) -> float:
        return bytes_to_gb(self.active_bytes)

    @property
    def lifetime_gb(self) -> float:
        return bytes_to_gb(self.lifetime_bytes)

    @property
    def used_gb(self) -> float:
        return self.lifetime_gb

    @property
    def remaining_gb(self) -> float:
        return bytes_to_gb(self.remaining_bytes)


def format_max_clients_line(st: QuotaStatus) -> str:
    """Persian line for reseller welcome / account status."""
    if st.max_clients is None:
        return "نامحدود"
    return f"{st.max_clients} سرویس (فعلی: {st.client_count})"


def format_max_clients_admin(st: QuotaStatus) -> str:
    """Short label for admin reseller list."""
    if st.max_clients is None:
        return "نامحدود"
    return str(st.max_clients)


class QuotaExceeded(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class QuotaService:
    def __init__(
        self,
        reseller_repo: ResellerRepository,
        panel_repo: ResellerPanelRepository | None = None,
    ) -> None:
        self.repo = reseller_repo
        self.panel_repo = panel_repo or ResellerPanelRepository(reseller_repo.session)

    async def _get_assignment(
        self, reseller: Reseller, panel_id: int
    ) -> ResellerPanel:
        row = await self.panel_repo.get(reseller.telegram_id, panel_id)
        if not row:
            raise QuotaExceeded("این پنل به حساب شما اختصاص داده نشده.")
        return row

    async def global_status(self, reseller: Reseller) -> QuotaStatus:
        """Unified quota pool across all panels (source: resellers row)."""
        lifetime = int(reseller.lifetime_allocated_bytes or 0)
        quota = int(reseller.quota_bytes or 0)
        active = await self.repo.active_bytes(reseller.telegram_id)
        count = await self.repo.client_count(reseller.telegram_id)
        remaining = max(0, quota - lifetime)
        return QuotaStatus(
            quota_bytes=quota,
            active_bytes=active,
            lifetime_bytes=lifetime,
            remaining_bytes=remaining,
            client_count=count,
            max_clients=reseller.max_clients,
            panel_id=None,
        )

    async def status(
        self, reseller: Reseller, panel_id: int | None = None
    ) -> QuotaStatus:
        """Global quota with optional per-panel client_count and max_clients."""
        global_st = await self.global_status(reseller)
        if panel_id is None:
            return global_st
        assignment = await self._get_assignment(reseller, panel_id)
        active = await self.repo.active_bytes_on_panel(
            reseller.telegram_id, panel_id
        )
        count = await self.repo.client_count_on_panel(
            reseller.telegram_id, panel_id
        )
        return QuotaStatus(
            quota_bytes=global_st.quota_bytes,
            active_bytes=active,
            lifetime_bytes=global_st.lifetime_bytes,
            remaining_bytes=global_st.remaining_bytes,
            client_count=count,
            max_clients=assignment.max_clients,
            panel_id=panel_id,
        )

    async def validate_create(
        self,
        reseller: Reseller,
        panel_id: int,
        volume_gb: float,
        inbound_ids: list[int],
    ) -> int:
        if not reseller.is_active:
            raise QuotaExceeded("حساب ریسلر غیرفعال است.")

        assignment = await self._get_assignment(reseller, panel_id)
        if not assignment.is_active:
            raise QuotaExceeded("ساخت کلاینت جدید روی این پنل ممنوع است.")
        allowed = set(json.loads(assignment.allowed_inbound_ids))
        for ib in inbound_ids:
            if ib not in allowed:
                raise QuotaExceeded(f"اینباند {ib} برای شما مجاز نیست.")

        try:
            validate_client_volume_gb(volume_gb)
        except ValueError as e:
            raise QuotaExceeded(str(e)) from e

        allocated = gb_to_bytes(volume_gb)
        if allocated <= 0:
            raise QuotaExceeded("حجم باید بزرگ‌تر از صفر باشد.")

        st = await self.status(reseller, panel_id)
        if st.max_clients is not None and st.client_count >= st.max_clients:
            raise QuotaExceeded("به سقف تعداد سرویس روی این پنل رسیده‌اید.")

        if allocated > st.remaining_bytes:
            raise QuotaExceeded(
                f"حجم درخواستی ({bytes_to_gb(allocated)} GB) بیشتر از باقی‌مانده "
                f"({st.remaining_gb} GB) است."
            )
        return allocated

    async def validate_add_traffic(
        self, reseller: Reseller, panel_id: int, volume_gb: float
    ) -> int:
        if not reseller.is_active:
            raise QuotaExceeded("حساب ریسلر غیرفعال است.")

        await self._get_assignment(reseller, panel_id)
        allocated = gb_to_bytes(volume_gb)
        if allocated <= 0:
            raise QuotaExceeded("حجم باید بزرگ‌تر از صفر باشد.")

        st = await self.global_status(reseller)
        if allocated > st.remaining_bytes:
            raise QuotaExceeded(
                f"حجم درخواستی ({bytes_to_gb(allocated)} GB) بیشتر از باقی‌مانده "
                f"({st.remaining_gb} GB) است."
            )
        return allocated

    def validate_remove_traffic(
        self,
        reseller: Reseller,
        volume_gb: float,
        *,
        current_allocated_bytes: int,
        used_bytes: int,
    ) -> int:
        if not reseller.is_active:
            raise QuotaExceeded("حساب ریسلر غیرفعال است.")

        removed = gb_to_bytes(volume_gb)
        if removed <= 0:
            raise QuotaExceeded("حجم باید بزرگ‌تر از صفر باشد.")

        if removed > current_allocated_bytes:
            raise QuotaExceeded(
                f"حجم درخواستی ({bytes_to_gb(removed)} GB) بیشتر از سقف فعلی "
                f"({bytes_to_gb(current_allocated_bytes)} GB) است."
            )

        new_total = current_allocated_bytes - removed
        if new_total < used_bytes:
            raise QuotaExceeded(
                f"سقف جدید ({bytes_to_gb(new_total)} GB) کمتر از مصرف فعلی "
                f"({bytes_to_gb(used_bytes)} GB) است."
            )
        return removed
