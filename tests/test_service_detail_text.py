"""Tests for the service detail summary (usage comes free with the status call)."""

from bot.handlers.reseller import ServiceDetail, _service_detail_text
from xui.client import gb_to_bytes


def _detail(**kw) -> ServiceDetail:
    base = dict(
        email="ali-client-x",
        enabled=True,
        expiry_ms=0,
        used_bytes=gb_to_bytes(12),
        total_bytes=gb_to_bytes(50),
    )
    base.update(kw)
    return ServiceDetail(**base)  # type: ignore[arg-type]


def test_shows_usage_and_progress_bar() -> None:
    text = _service_detail_text(_detail())
    assert "12.00 GB" in text
    assert "50.00 GB" in text
    assert "24%" in text


def test_unlimited_total_omits_progress_bar() -> None:
    text = _service_detail_text(_detail(total_bytes=0))
    assert "سقف نامحدود" in text
    assert "%" not in text


def test_unknown_usage_when_panel_call_failed() -> None:
    text = _service_detail_text(_detail(used_bytes=None))
    assert "نامشخص" in text
    assert "%" not in text


def test_disabled_status_is_shown() -> None:
    assert "غیرفعال" in _service_detail_text(_detail(enabled=False))


def test_usage_line_stays_a_single_used_of_total_phrase() -> None:
    """Bidi guard for the line this change adds (see commit 0d9632d).

    Cramming independent numeric fields onto one RTL line is what garbled the
    plan listings. "used از total" is one left-to-right phrase and is fine, but
    nothing further may be appended to it.
    """
    text = _service_detail_text(_detail(expiry_ms=1_800_000_000_000))
    usage_line = next(ln for ln in text.split("\n") if ln.startswith("مصرف:"))
    runs = [w for w in usage_line.split() if any(c.isdigit() for c in w)]
    assert len(runs) == 2, usage_line


def test_each_field_is_on_its_own_line() -> None:
    text = _service_detail_text(_detail(expiry_ms=1_800_000_000_000))
    lines = text.split("\n")
    for label in ("سرویس:", "وضعیت:", "مصرف:", "انقضا:"):
        assert sum(ln.startswith(label) for ln in lines) == 1, label
