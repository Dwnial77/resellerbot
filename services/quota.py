import json
from dataclasses import dataclass

from db.models import Reseller
from db.repository import ResellerRepository
from xui.client import bytes_to_gb, gb_to_bytes


@dataclass
class QuotaStatus:
    quota_bytes: int
    used_bytes: int
    remaining_bytes: int
    client_count: int
    max_clients: int | None

    @property
    def quota_gb(self) -> float:
        return bytes_to_gb(self.quota_bytes)

    @property
    def used_gb(self) -> float:
        return bytes_to_gb(self.used_bytes)

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
    def __init__(self, repo: ResellerRepository) -> None:
        self.repo = repo

    async def status(self, reseller: Reseller) -> QuotaStatus:
        used = await self.repo.used_bytes(reseller.telegram_id)
        count = await self.repo.client_count(reseller.telegram_id)
        remaining = max(0, reseller.quota_bytes - used)
        return QuotaStatus(
            quota_bytes=reseller.quota_bytes,
            used_bytes=used,
            remaining_bytes=remaining,
            client_count=count,
            max_clients=reseller.max_clients,
        )

    async def validate_create(
        self,
        reseller: Reseller,
        volume_gb: float,
        inbound_ids: list[int],
    ) -> int:
        if not reseller.is_active:
            raise QuotaExceeded("حساب ریسلر غیرفعال است.")

        allowed = set(json.loads(reseller.allowed_inbound_ids))
        for ib in inbound_ids:
            if ib not in allowed:
                raise QuotaExceeded(f"اینباند {ib} برای شما مجاز نیست.")

        allocated = gb_to_bytes(volume_gb)
        if allocated <= 0:
            raise QuotaExceeded("حجم باید بزرگ‌تر از صفر باشد.")

        st = await self.status(reseller)
        if st.max_clients is not None and st.client_count >= st.max_clients:
            raise QuotaExceeded("به سقف تعداد سرویس رسیده‌اید.")

        if allocated > st.remaining_bytes:
            raise QuotaExceeded(
                f"حجم درخواستی ({bytes_to_gb(allocated)} GB) بیشتر از باقی‌مانده "
                f"({st.remaining_gb} GB) است."
            )
        return allocated
