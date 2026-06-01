from db.models import Reseller
from bot.keyboards.common import reseller_admin_hub_kb, reseller_view_kb


def test_reseller_view_kb_builds_without_error() -> None:
    kb = reseller_view_kb(123, is_active=True, can_change_panel=True)
    assert len(kb.inline_keyboard) == 5
    assert kb.inline_keyboard[1][0].callback_data == "rsl:edit:123"
    kb2 = reseller_view_kb(123, is_active=False, can_change_panel=False)
    assert len(kb2.inline_keyboard) == 4


def test_edit_callback_data_under_64_bytes() -> None:
    tg_id = 5266810479
    assert len(f"rsl:ev:quota:{tg_id}") < 64
    assert len(f"rsl:eq:100:{tg_id}") < 64


def test_reseller_hub_kb_add_button() -> None:
    r = Reseller(
        telegram_id=123,
        panel_id=1,
        quota_bytes=0,
        allowed_inbound_ids="[1]",
        is_active=True,
    )
    kb = reseller_admin_hub_kb([r], {1: "Main"})
    rows = kb.inline_keyboard
    assert rows[-1][0].callback_data == "rsl:add"
    assert rows[0][0].callback_data == "rsl:view:123"
