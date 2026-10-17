"""RTL-safe Persian labels for guest plan buttons and lists."""

import re

from bot.handlers.guest import _plan_list_text
from bot.keyboards.common import guest_plan_button_label, guest_plan_picker_kb
from bot.texts import fa as t
from bot.utils.fa_text import RLM, fa_days, fa_digits, fa_gb, fa_toman, rtl
from db.models import Plan


def _plan(name: str = "آلمان", **kw) -> Plan:
    base = dict(id=7, name=name, volume_gb=50, expiry_days=30, price_toman=180000)
    base.update(kw)
    return Plan(**base)


def test_persian_number_helpers() -> None:
    assert fa_digits("2026/10/17") == "۲۰۲۶/۱۰/۱۷"
    assert fa_toman(180000) == "۱۸۰٬۰۰۰"
    assert fa_gb(50) == "۵۰ گیگ" and fa_gb(2.5) == "۲.۵ گیگ"
    assert fa_days(30) == "۳۰ روز" and fa_days(0) == "نامحدود"
    assert rtl(rtl("x")) == RLM + "x"


def test_plan_button_has_no_ltr_runs_outside_the_name() -> None:
    for name in ("آلمان", "🇩🇪", "Germany VIP"):
        label = guest_plan_button_label(_plan(name))
        assert label.startswith(RLM)
        rest = label.replace(name, "")
        assert not re.search(r"[0-9A-Za-z]", rest), label
        # Name is closed with an RLM so a Latin/flag name can't merge with the volume.
        assert f"{name}{RLM} | " in label


def test_plan_picker_callbacks_unchanged() -> None:
    kb = guest_plan_picker_kb([_plan()])
    assert kb.inline_keyboard[0][0].callback_data == "gplan:7"


def test_plan_list_lines_are_rtl_and_one_field_per_line() -> None:
    text = _plan_list_text(t.GUEST_PLAN_LIST_HEADER, [_plan("🇩🇪", volume_gb=100)])
    plan_lines = [l for l in text.split("\n") if l.strip()][1:-1]
    assert len(plan_lines) == 4
    assert all(l.startswith(RLM) for l in plan_lines)
    assert "۱۰۰ گیگ" in plan_lines[1] and "۳۰ روز" in plan_lines[2]
    assert "۱۸۰٬۰۰۰ تومان" in plan_lines[3]
