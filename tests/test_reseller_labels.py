from db.models import Reseller
from services.reseller_labels import (
    InvalidDisplayNameError,
    normalize_display_name,
    panel_group_name,
    reseller_label,
)


def test_normalize_display_name() -> None:
    assert normalize_display_name("Ali") == "ali"
    assert normalize_display_name("reza_1") == "reza_1"


def test_normalize_rejects_short() -> None:
    try:
        normalize_display_name("a")
        raise AssertionError("expected InvalidDisplayNameError")
    except InvalidDisplayNameError:
        pass


def test_panel_group_name() -> None:
    r = Reseller(
        telegram_id=5266810479,
        display_name="ali",
        quota_bytes=0,
        allowed_inbound_ids="[1]",
    )
    assert panel_group_name(r) == "ali-5266810479"


def test_panel_group_name_without_display() -> None:
    r = Reseller(
        telegram_id=123,
        display_name=None,
        quota_bytes=0,
        allowed_inbound_ids="[1]",
    )
    assert panel_group_name(r) == "123"


def test_reseller_label() -> None:
    r = Reseller(
        telegram_id=5266810479,
        display_name="ali",
        quota_bytes=0,
        allowed_inbound_ids="[1]",
    )
    assert reseller_label(r) == "ali (5266810479)"
