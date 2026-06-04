from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

GB = 1024**3
MB = 1024**2


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_traffic_data(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        if not data:
            return {}
        data = data[0]
    if isinstance(data, dict):
        return data
    return {}


def client_traffic_used_bytes(data: Any) -> int:
    row = normalize_traffic_data(data)
    return _coerce_int(row.get("up")) + _coerce_int(row.get("down"))


def format_bytes(value: int) -> str:
    n = max(0, int(value))
    if n >= GB:
        return f"{n / GB:.2f} GB"
    if n >= MB:
        return f"{n / MB:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


def progress_bar(used: int, total: int, width: int = 10) -> tuple[str, int]:
    if total <= 0:
        return "░" * width, 0
    ratio = min(max(used / total, 0.0), 1.0)
    filled = int(round(ratio * width))
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    percent = int(round(ratio * 100))
    return bar, percent


def format_expiry(expiry_ms: int) -> str:
    if expiry_ms <= 0:
        return "نامحدود"
    try:
        dt = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).astimezone()
    except (OSError, OverflowError, ValueError):
        return "نامشخص"
    now = datetime.now(tz=dt.tzinfo)
    if dt <= now:
        return f"منقضی شده ({dt.strftime('%Y-%m-%d %H:%M')})"
    days_left = (dt - now).days
    date_str = dt.strftime("%Y-%m-%d %H:%M")
    if days_left > 0:
        return f"{date_str} ({days_left} روز مانده)"
    hours_left = int((dt - now).total_seconds() // 3600)
    if hours_left > 0:
        return f"{date_str} ({hours_left} ساعت مانده)"
    return date_str


def format_last_online(last_online_ms: int) -> str:
    if last_online_ms <= 0:
        return "هنوز متصل نشده"
    try:
        dt = datetime.fromtimestamp(last_online_ms / 1000, tz=timezone.utc).astimezone()
    except (OSError, OverflowError, ValueError):
        return "نامشخص"
    return dt.strftime("%Y-%m-%d %H:%M")


def format_traffic_message(email: str, data: Any) -> str:
    row = normalize_traffic_data(data)

    up = _coerce_int(row.get("up"))
    down = _coerce_int(row.get("down"))
    total = _coerce_int(row.get("total"))
    used = client_traffic_used_bytes(row)
    enable = row.get("enable", True)
    inbound_id = row.get("inboundId", row.get("inbound_id", "—"))
    sub_id = row.get("subId") or row.get("sub_id") or "—"
    expiry_ms = _coerce_int(row.get("expiryTime", row.get("expiry_time")))
    last_online_ms = _coerce_int(row.get("lastOnline", row.get("last_online")))

    status = "فعال" if enable else "غیرفعال"
    status_icon = "✅" if enable else "⛔"

    if total > 0:
        quota_line = f"{format_bytes(used)} از {format_bytes(total)}"
        bar, percent = progress_bar(used, total)
        bar_line = f"[{bar}] {percent}%"
    else:
        quota_line = f"{format_bytes(used)} (سقف نامحدود)"
        bar_line = ""

    lines = [
        "📊 ترافیک سرویس",
        f"ایمیل: {email}",
        "",
        f"وضعیت: {status_icon} {status}",
        f"اینباند: {inbound_id}",
        f"شناسه ساب: {sub_id}",
        "",
        f"⬆️ آپلود: {format_bytes(up)}",
        f"⬇️ دانلود: {format_bytes(down)}",
        f"📦 مصرف کل: {quota_line}",
    ]
    if bar_line:
        lines.append(bar_line)
    lines.extend(
        [
            "",
            f"⏳ انقضا: {format_expiry(expiry_ms)}",
            f"🕐 آخرین اتصال: {format_last_online(last_online_ms)}",
        ]
    )
    return "\n".join(lines)
