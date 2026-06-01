"""Tests for reseller service edit validation helpers."""

from bot.utils.edit_service import (
    InvalidEditInputError,
    format_limit_ip_label,
    normalize_comment,
    validate_comment,
    validate_limit_ip,
)


def test_validate_limit_ip_ok() -> None:
    assert validate_limit_ip(0) == 0
    assert validate_limit_ip(5) == 5


def test_validate_limit_ip_negative() -> None:
    try:
        validate_limit_ip(-1)
        assert False, "expected error"
    except InvalidEditInputError:
        pass


def test_validate_comment_trim_and_limit() -> None:
    assert validate_comment("  hello  ") == "hello"
    long_text = "a" * 250
    assert len(validate_comment(long_text)) == 200


def test_format_limit_ip_label() -> None:
    assert format_limit_ip_label(0) == "نامحدود"
    assert format_limit_ip_label(3) == "3"


if __name__ == "__main__":
    test_validate_limit_ip_ok()
    test_validate_limit_ip_negative()
    test_validate_comment_trim_and_limit()
    test_format_limit_ip_label()
    print("ok")
