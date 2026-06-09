import asyncio
from unittest.mock import AsyncMock

from bot.utils.report_format import (
    format_progress_bar,
    format_progress_bar_line,
    format_report_button_label,
    format_used_percent,
)
from db.models import Reseller, ResellerPanel
from services.quota import QuotaService


def test_format_used_percent() -> None:
    assert format_used_percent(50, 100) == "50%"
    assert format_used_percent(0, 100) == "0%"
    assert format_used_percent(10, 0) == "—"


def test_format_progress_bar() -> None:
    assert format_progress_bar(0) == "░░░░░░░░░░"
    assert format_progress_bar(50) == "▓▓▓▓▓░░░░░"
    assert format_progress_bar(100) == "▓▓▓▓▓▓▓▓▓▓"
    assert format_progress_bar(None) == "—"


def test_format_progress_bar_line() -> None:
    assert format_progress_bar_line(45) == "▓▓▓▓░░░░░░ 45%"
    assert format_progress_bar_line(None) == "—"


def test_format_report_button_label_truncates() -> None:
    long_name = "a" * 60
    label = format_report_button_label(
        long_name,
        is_active=True,
        client_count=3,
        percent=50,
        max_len=64,
    )
    assert len(label) <= 64
    assert label.endswith("...")


def test_quota_status_for_report() -> None:
    async def _run() -> None:
        reseller = Reseller(
            telegram_id=100,
            panel_id=1,
            quota_bytes=10 * 1024**3,
            lifetime_allocated_bytes=3 * 1024**3,
            allowed_inbound_ids="[1]",
            attach_inbound_ids="[1]",
            max_clients=5,
        )
        assignment = ResellerPanel(
            reseller_tg_id=100,
            panel_id=1,
            quota_bytes=10 * 1024**3,
            lifetime_allocated_bytes=3 * 1024**3,
            allowed_inbound_ids="[1]",
            is_active=True,
        )
        repo = AsyncMock()
        repo.active_bytes_on_panel = AsyncMock(return_value=2 * 1024**3)
        repo.client_count_on_panel = AsyncMock(return_value=2)
        panel_repo = AsyncMock()
        panel_repo.get = AsyncMock(return_value=assignment)

        st = await QuotaService(repo, panel_repo).status(reseller, 1)
        assert st.client_count == 2
        assert st.quota_gb == 10.0
        assert st.lifetime_gb == 3.0
        assert st.active_gb == 2.0
        assert st.remaining_gb == 7.0
        assert format_used_percent(st.lifetime_bytes, st.quota_bytes) == "30%"

    asyncio.run(_run())
