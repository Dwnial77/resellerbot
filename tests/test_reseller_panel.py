import pytest

from bot.handlers.admin import AddResellerParsed, _parse_add_reseller


def test_parse_legacy_unnamed() -> None:
    p = _parse_add_reseller("123456789 100 1 2")
    assert p == AddResellerParsed(123456789, None, 1, 100.0, [1, 2])


def test_parse_with_panel_unnamed() -> None:
    p = _parse_add_reseller("123456789 2 50 1")
    assert p == AddResellerParsed(123456789, None, 2, 50.0, [1])


def test_parse_legacy_named() -> None:
    p = _parse_add_reseller("123456789 ali 100 1")
    assert p == AddResellerParsed(123456789, "ali", 1, 100.0, [1])


def test_parse_named_with_panel() -> None:
    p = _parse_add_reseller("5266810479 ali 2 100 1 3")
    assert p == AddResellerParsed(5266810479, "ali", 2, 100.0, [1, 3])


def test_parse_too_few_parts() -> None:
    with pytest.raises(ValueError):
        _parse_add_reseller("123 100")
