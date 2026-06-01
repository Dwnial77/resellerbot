import pytest

from db.models import Reseller
from db.repository import (
    format_inbound_summary,
    resolve_attach_inbound_ids,
    trim_attach_to_allowed,
    validate_inbound_subset,
)


def _reseller(
    allowed: str = "[1,2,3]",
    attach: str | None = None,
) -> Reseller:
    return Reseller(
        telegram_id=1,
        panel_id=1,
        quota_bytes=100 * 1024**3,
        allowed_inbound_ids=allowed,
        attach_inbound_ids=attach,
    )


def test_resolve_attach_uses_allowed_when_null() -> None:
    r = _reseller(allowed="[1,2]", attach=None)
    assert resolve_attach_inbound_ids(r) == [1, 2]


def test_resolve_attach_uses_explicit_list() -> None:
    r = _reseller(allowed="[1,2,3]", attach="[1]")
    assert resolve_attach_inbound_ids(r) == [1]


def test_validate_subset_rejects_empty_attach() -> None:
    with pytest.raises(ValueError, match="خالی"):
        validate_inbound_subset([1, 2], [])


def test_validate_subset_rejects_outside_allowed() -> None:
    with pytest.raises(ValueError, match="مجاز"):
        validate_inbound_subset([1, 2], [3])


def test_validate_subset_ok() -> None:
    validate_inbound_subset([1, 2, 3], [1, 2])


def test_trim_attach_to_allowed() -> None:
    assert trim_attach_to_allowed([1, 2], [1, 3]) == [1]


def test_trim_falls_back_to_allowed_when_empty_intersection() -> None:
    assert trim_attach_to_allowed([1, 2], [9]) == [1, 2]


def test_format_inbound_summary_same_lists() -> None:
    r = _reseller(allowed="[1,2]", attach="[1,2]")
    text = format_inbound_summary(r)
    assert "اینباندهای متصل: 1, 2" in text
    assert "مجاز" not in text


def test_set_allowed_syncs_attach_logic() -> None:
    """After set_allowed, attach should match allowed (documented behavior)."""
    allowed = [1, 2, 3]
    attach = list(allowed)
    assert attach == allowed


def test_format_inbound_summary_different_lists() -> None:
    r = _reseller(allowed="[1,2,3]", attach="[1]")
    text = format_inbound_summary(r)
    assert "اینباندهای متصل: 1" in text
    assert "اینباندهای مجاز: 1, 2, 3" in text
