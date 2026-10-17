"""Tests for paginated reseller service list keyboard."""

import time

from bot.keyboards.common import (
    SERVICES_PAGE_SIZE,
    service_button_label,
    service_list_kb,
)
from bot.keyboards.labels import NEXT_PAGE, PREV_PAGE
from db.models import ClientRecord

_DAY_MS = 86_400_000


def _record(email: str, *, record_id: int = 1, expiry_ms: int = 0) -> ClientRecord:
    return ClientRecord(
        id=record_id,
        reseller_tg_id=100,
        panel_id=1,
        email=email,
        inbound_ids="[1]",
        allocated_bytes=0,
        expiry_time=expiry_ms,
    )


def _records(count: int) -> list[ClientRecord]:
    return [_record(f"user{i}", record_id=i) for i in range(count)]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _service_callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
        and not btn.callback_data.startswith("svc:pg:")
        and not btn.callback_data.startswith("svc:search")
    ]


def _nav_callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("svc:pg:")
    ]


def test_single_page_no_navigation() -> None:
    kb = service_list_kb(_records(5), page=0)
    assert len(_service_callbacks(kb)) == 5
    assert _nav_callbacks(kb) == []


def test_two_pages_first_page() -> None:
    kb = service_list_kb(_records(9), page=0)
    assert len(_service_callbacks(kb)) == SERVICES_PAGE_SIZE
    assert _service_callbacks(kb)[0] == "svc:0"
    assert _service_callbacks(kb)[-1] == "svc:7"
    nav = _nav_callbacks(kb)
    assert "svc:pg:0" in nav
    assert "svc:pg:1" in nav
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert NEXT_PAGE in texts
    assert PREV_PAGE not in texts


def test_two_pages_second_page() -> None:
    kb = service_list_kb(_records(9), page=1)
    assert _service_callbacks(kb) == ["svc:8"]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert PREV_PAGE in texts
    assert NEXT_PAGE not in texts


def test_three_pages_last_page() -> None:
    kb = service_list_kb(_records(24), page=2)
    assert len(_service_callbacks(kb)) == 8
    assert _service_callbacks(kb)[0] == "svc:16"
    assert _service_callbacks(kb)[-1] == "svc:23"
    nav = _nav_callbacks(kb)
    assert "svc:pg:1" in nav
    assert "svc:pg:2" in nav
    assert "svc:pg:3" not in nav


def _search_callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("svc:search")
    ]


def test_no_query_shows_only_search_button() -> None:
    kb = service_list_kb(_records(3), page=0)
    assert _search_callbacks(kb) == ["svc:search"]


def test_active_query_shows_search_and_clear_buttons() -> None:
    kb = service_list_kb(_records(3), page=0, query="user1")
    assert set(_search_callbacks(kb)) == {"svc:search", "svc:search:clear"}


def test_empty_result_with_query_still_offers_clear() -> None:
    kb = service_list_kb([], page=0, query="nomatch")
    assert _service_callbacks(kb) == []
    assert set(_search_callbacks(kb)) == {"svc:search", "svc:search:clear"}


def test_button_label_marks_expired() -> None:
    label = service_button_label(_record("ali-x", expiry_ms=_now_ms() - _DAY_MS))
    assert label.startswith("❌ ")
    assert "ali-x" in label


def test_button_label_marks_expiring_soon() -> None:
    label = service_button_label(_record("ali-x", expiry_ms=_now_ms() + 2 * _DAY_MS))
    assert label.startswith("⚠️ ")


def test_button_label_plain_when_healthy() -> None:
    assert service_button_label(_record("ali-x", expiry_ms=_now_ms() + 30 * _DAY_MS)) == "ali-x"


def test_button_label_plain_when_unlimited() -> None:
    assert service_button_label(_record("ali-x", expiry_ms=0)) == "ali-x"


def test_button_labels_never_contain_digits() -> None:
    """Digits on an RTL button line get reordered by Telegram's bidi renderer
    (the bug fixed in commit 0d9632d) — counts belong in the message text."""
    now = _now_ms()
    records = [
        _record("aaa", record_id=1, expiry_ms=now - _DAY_MS),
        _record("bbb", record_id=2, expiry_ms=now + _DAY_MS),
        _record("ccc", record_id=3, expiry_ms=0),
    ]
    for record in records:
        assert not any(ch.isdigit() for ch in service_button_label(record))


def test_long_email_is_truncated_but_callback_stays_short() -> None:
    record = _record("a" * 72, record_id=4321)
    kb = service_list_kb([record], page=0)
    button = kb.inline_keyboard[0][0]
    assert button.text.endswith("...")
    assert button.callback_data == "svc:4321"
