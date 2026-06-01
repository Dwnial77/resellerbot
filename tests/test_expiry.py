"""Tests for expiry helpers."""

import time

from bot.utils.expiry import InvalidExpiryInputError, parse_expiry_date
from xui.client import resolve_expiry_after_add_days


def test_resolve_expiry_from_future_current() -> None:
    now_ms = int(time.time() * 1000)
    current = now_ms + 10 * 86400 * 1000
    new_ms = resolve_expiry_after_add_days(current, 5)
    assert new_ms == current + 5 * 86400 * 1000


def test_resolve_expiry_from_expired() -> None:
    now_ms = int(time.time() * 1000)
    current = now_ms - 86400 * 1000
    new_ms = resolve_expiry_after_add_days(current, 7)
    assert new_ms >= now_ms + 6 * 86400 * 1000
    assert new_ms <= now_ms + 8 * 86400 * 1000


def test_resolve_expiry_unlimited_base() -> None:
    now_ms = int(time.time() * 1000)
    new_ms = resolve_expiry_after_add_days(0, 30)
    assert new_ms >= now_ms + 29 * 86400 * 1000


def test_parse_expiry_date_zero() -> None:
    assert parse_expiry_date("0") == 0


def test_parse_expiry_date_invalid() -> None:
    try:
        parse_expiry_date("31-12-2026")
        assert False, "expected error"
    except InvalidExpiryInputError:
        pass


def test_parse_expiry_date_valid() -> None:
    ms = parse_expiry_date("2030-06-15")
    assert ms > 0


if __name__ == "__main__":
    test_resolve_expiry_from_future_current()
    test_resolve_expiry_from_expired()
    test_resolve_expiry_unlimited_base()
    test_parse_expiry_date_zero()
    test_parse_expiry_date_invalid()
    test_parse_expiry_date_valid()
    print("ok")
