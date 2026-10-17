"""Tests for expiry classification used by the service list icons."""

import time

from bot.utils.format_traffic import (
    EXPIRY_EXPIRED,
    EXPIRY_OK,
    EXPIRY_SOON,
    EXPIRY_SOON_DAYS,
    expiry_status,
)

_DAY_MS = 86_400_000


def _now_ms() -> int:
    return int(time.time() * 1000)


def test_unlimited_is_ok() -> None:
    assert expiry_status(0) == EXPIRY_OK


def test_negative_is_treated_as_unlimited() -> None:
    assert expiry_status(-1) == EXPIRY_OK


def test_past_is_expired() -> None:
    assert expiry_status(_now_ms() - _DAY_MS) == EXPIRY_EXPIRED


def test_just_past_is_expired() -> None:
    assert expiry_status(_now_ms() - 1000) == EXPIRY_EXPIRED


def test_within_threshold_is_soon() -> None:
    assert expiry_status(_now_ms() + 2 * _DAY_MS) == EXPIRY_SOON


def test_just_inside_threshold_is_soon() -> None:
    almost = _now_ms() + EXPIRY_SOON_DAYS * _DAY_MS - 60_000
    assert expiry_status(almost) == EXPIRY_SOON


def test_just_outside_threshold_is_ok() -> None:
    beyond = _now_ms() + EXPIRY_SOON_DAYS * _DAY_MS + 60_000
    assert expiry_status(beyond) == EXPIRY_OK


def test_far_future_is_ok() -> None:
    assert expiry_status(_now_ms() + 365 * _DAY_MS) == EXPIRY_OK


def test_absurd_timestamp_does_not_raise() -> None:
    assert expiry_status(10**20) == EXPIRY_OK
