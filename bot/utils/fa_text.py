"""Right-to-left safe Persian formatting for user-facing labels.

Telegram lays out each line with the Unicode bidi algorithm: ASCII digits and
Latin units ("50GB") form left-to-right runs that pull neighbouring separators
out of place, and a line whose first strong character is Latin or that starts
with an emoji gets a left-to-right base direction. Persian digits/units keep a
line in logical order, and a leading RLM forces the right-to-left base.
"""

from __future__ import annotations

RLM = "‏"
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_FA_THOUSANDS = "٬"


def fa_digits(text: object) -> str:
    return str(text).translate(_FA_DIGITS)


def rtl(text: str) -> str:
    """Force a right-to-left base direction for one line (button or text line)."""
    return text if text.startswith(RLM) else RLM + text


def fa_toman(amount: int | float) -> str:
    """180000 -> '۱۸۰٬۰۰۰'."""
    return fa_digits(f"{int(amount):,}".replace(",", _FA_THOUSANDS))


def fa_gb(volume_gb: float) -> str:
    """50 -> '۵۰ گیگ', 2.5 -> '۲.۵ گیگ'."""
    return f"{fa_digits(f'{float(volume_gb):g}')} گیگ"


def fa_days(days: int) -> str:
    return f"{fa_digits(days)} روز" if days > 0 else "نامحدود"
