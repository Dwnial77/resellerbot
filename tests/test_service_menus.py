"""Tests for the reseller service detail / edit menu layout."""

from bot.keyboards.common import service_detail_kb, service_edit_kb

TELEGRAM_CALLBACK_MAX = 64
RECORD_ID = 42


def _callbacks(kb) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]


def test_detail_menu_has_merged_link_and_qr() -> None:
    cbs = _callbacks(service_detail_kb(RECORD_ID))
    assert f"linkqr:{RECORD_ID}" in cbs
    assert not any(c.startswith("link:") or c.startswith("qr_menu:") for c in cbs)


def test_detail_menu_offers_renew_not_expiry() -> None:
    cbs = _callbacks(service_detail_kb(RECORD_ID))
    assert f"renew:{RECORD_ID}" in cbs
    assert not any(c.startswith("exp:") for c in cbs)


def test_detail_menu_no_longer_has_traffic_adjustment() -> None:
    cbs = _callbacks(service_detail_kb(RECORD_ID))
    assert not any(c.startswith("traf:") or c.startswith("trafd:") for c in cbs)


def test_detail_menu_toggle_follows_enabled_state() -> None:
    assert f"disable:{RECORD_ID}" in _callbacks(
        service_detail_kb(RECORD_ID, enabled=True)
    )
    assert f"enable:{RECORD_ID}" in _callbacks(
        service_detail_kb(RECORD_ID, enabled=False)
    )


def test_edit_menu_owns_traffic_and_expiry() -> None:
    cbs = _callbacks(service_edit_kb(RECORD_ID))
    for expected in (
        f"traf:{RECORD_ID}",
        f"trafd:{RECORD_ID}",
        f"exp:{RECORD_ID}",
    ):
        assert expected in cbs


def test_edit_menu_has_rename_and_sub_link() -> None:
    cbs = _callbacks(service_edit_kb(RECORD_ID))
    assert f"edit_name:{RECORD_ID}" in cbs
    assert f"edit_sub:{RECORD_ID}" in cbs


def test_menu_callbacks_fit_telegram_limit() -> None:
    """Now that callbacks carry the record id, service name length is irrelevant.

    A 19-digit id is past SQLite's INTEGER range, so this is the true worst case.
    """
    record_id = 9_223_372_036_854_775_807
    for kb in (service_detail_kb(record_id), service_edit_kb(record_id)):
        for cb in _callbacks(kb):
            assert len(cb.encode()) <= TELEGRAM_CALLBACK_MAX, cb


# Fixed navigation targets, not references to a particular service.
_CONSTANT_CALLBACKS = {"svc:back"}


def test_menu_callbacks_are_id_keyed_not_email_keyed() -> None:
    """Email is mutable (rename), so it must not appear in callback data."""
    for kb in (service_detail_kb(RECORD_ID), service_edit_kb(RECORD_ID)):
        for cb in _callbacks(kb):
            if cb in _CONSTANT_CALLBACKS:
                continue
            prefix, _, suffix = cb.rpartition(":")
            assert prefix, cb
            assert suffix.isdigit(), cb
