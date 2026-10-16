"""Parse numeric user input (GB volumes, day counts)."""

from __future__ import annotations

import math

# Upper bound for any day count (≈10 years); larger values overflow expiry math.
MAX_DAYS = 3650


def parse_number(raw: object) -> float:
    """Parse a decimal number ("10", "2.5", "2,5", Persian digits).

    Raises ValueError for anything that is not a finite number (nan/inf too).
    """
    text = str(raw).strip().replace("٫", ".").replace(",", ".")
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"not a finite number: {raw!r}")
    return value


def parse_days(raw: object) -> int:
    """Parse a whole day count, rejecting values above MAX_DAYS."""
    value = int(str(raw).strip())
    if value > MAX_DAYS:
        raise ValueError(f"too many days: {value}")
    return value
