"""Format helpers for admin reseller reports."""

from __future__ import annotations


def usage_percent_int(used_bytes: int, quota_bytes: int) -> int | None:
    if quota_bytes <= 0:
        return None
    return min(100, round(used_bytes * 100 / quota_bytes))


def format_used_percent(used_bytes: int, quota_bytes: int) -> str:
    percent = usage_percent_int(used_bytes, quota_bytes)
    if percent is None:
        return "—"
    return f"{percent}%"


def format_progress_bar(percent: int | None, width: int = 10) -> str:
    if percent is None:
        return "—"
    filled = max(0, min(width, round(width * percent / 100)))
    return "▓" * filled + "░" * (width - filled)


def format_progress_bar_line(percent: int | None, width: int = 10) -> str:
    if percent is None:
        return "—"
    return f"{format_progress_bar(percent, width)} {percent}%"


def format_hub_totals(total: int, active: int) -> list[str]:
    """Aggregate header lines for the reseller hub, one number per line.

    The previous per-reseller summary line packed name, panel, status, service
    count and usage percent onto a single RTL line. Two numeric runs separated
    by Persian text get visually reordered by Telegram's bidi renderer — the
    same defect fixed for plan/template listings in commit 0d9632d. Per-reseller
    detail now lives on the buttons, whose labels are pure ASCII and safe.
    """
    lines = [f"تعداد کل: {total}"]
    if total:
        lines.append(f"فعال: {active}")
        inactive = total - active
        if inactive:
            lines.append(f"غیرفعال: {inactive}")
    return lines


def format_report_button_label(
    name: str,
    *,
    is_active: bool,
    client_count: int,
    percent: int | None,
    max_len: int = 64,
) -> str:
    dot = "🟢" if is_active else "🔴"
    pct = f"{percent}%" if percent is not None else "—"
    label = f"{dot} {name} · {client_count} · {pct}"
    if len(label) > max_len:
        label = label[: max_len - 3] + "..."
    return label
