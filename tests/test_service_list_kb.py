"""Tests for paginated reseller service list keyboard."""

from bot.keyboards.common import SERVICES_PAGE_SIZE, service_list_kb
from bot.keyboards.labels import NEXT_PAGE, PREV_PAGE


def _service_callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and not btn.callback_data.startswith("svc:pg:")
    ]


def _nav_callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("svc:pg:")
    ]


def test_single_page_no_navigation() -> None:
    emails = [f"user{i}" for i in range(5)]
    kb = service_list_kb(emails, page=0)
    assert len(_service_callbacks(kb)) == 5
    assert _nav_callbacks(kb) == []


def test_two_pages_first_page() -> None:
    emails = [f"user{i}" for i in range(9)]
    kb = service_list_kb(emails, page=0)
    assert len(_service_callbacks(kb)) == SERVICES_PAGE_SIZE
    assert _service_callbacks(kb)[0] == "svc:user0"
    assert _service_callbacks(kb)[-1] == "svc:user7"
    nav = _nav_callbacks(kb)
    assert "svc:pg:0" in nav
    assert "svc:pg:1" in nav
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert NEXT_PAGE in texts
    assert PREV_PAGE not in texts


def test_two_pages_second_page() -> None:
    emails = [f"user{i}" for i in range(9)]
    kb = service_list_kb(emails, page=1)
    assert _service_callbacks(kb) == ["svc:user8"]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert PREV_PAGE in texts
    assert NEXT_PAGE not in texts


def test_three_pages_last_page() -> None:
    emails = [f"user{i}" for i in range(24)]
    kb = service_list_kb(emails, page=2)
    assert len(_service_callbacks(kb)) == 8
    assert _service_callbacks(kb)[0] == "svc:user16"
    assert _service_callbacks(kb)[-1] == "svc:user23"
    nav = _nav_callbacks(kb)
    assert "svc:pg:1" in nav
    assert "svc:pg:2" in nav
    assert "svc:pg:3" not in nav
