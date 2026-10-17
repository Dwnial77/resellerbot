"""Parse and format expiry inputs for reseller flows."""

from __future__ import annotations

from datetime import datetime, time as dt_time, timezone

from bot.utils.numbers import MAX_DAYS


class InvalidExpiryInputError(ValueError):
    pass


def parse_expiry_date(text: str) -> int:
    """
    Parse YYYY-MM-DD or 0 (unlimited).
    Returns expiry timestamp in milliseconds (end of local day).
    """
    raw = (text or "").strip()
    if raw == "0":
        return 0
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as e:
        raise InvalidExpiryInputError(
            "فرمت تاریخ نامعتبر است. مثال: 2026-12-31 یا 0 برای نامحدود"
        ) from e
    now = datetime.now().astimezone()
    if day < now.date():
        # Past dates (and pre-1970 ones, which 3x-ui reads as a negative
        # "start on first use" duration) are never what the user wants.
        raise InvalidExpiryInputError("تاریخ انقضا نباید در گذشته باشد.")
    if (day - now.date()).days > MAX_DAYS:
        raise InvalidExpiryInputError(
            f"تاریخ انقضا حداکثر می‌تواند {MAX_DAYS} روز بعد باشد."
        )
    end_of_day = datetime.combine(day, dt_time(23, 59, 59), tzinfo=now.tzinfo)
    return int(end_of_day.timestamp() * 1000)
