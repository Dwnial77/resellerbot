import pytest

from bot.utils.expiry import InvalidExpiryInputError, parse_expiry_date
from bot.utils.numbers import MAX_DAYS, parse_days, parse_number


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "NaN", "1e400", "", "abc"])
def test_parse_number_rejects_non_finite_or_garbage(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_number(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [("10", 10.0), ("2,5", 2.5), ("۲٫۵", 2.5), (" 30 ", 30.0), ("-5", -5.0)],
)
def test_parse_number_accepts_decimals(raw: str, expected: float) -> None:
    assert parse_number(raw) == expected


def test_parse_days_caps_value() -> None:
    assert parse_days("۳۰") == 30
    assert parse_days(str(MAX_DAYS)) == MAX_DAYS
    with pytest.raises(ValueError):
        parse_days(str(MAX_DAYS + 1))
    with pytest.raises(ValueError):
        parse_days("1.5")


@pytest.mark.parametrize("raw", ["1900-01-01", "2000-01-01", "2999-01-01"])
def test_parse_expiry_date_rejects_past_and_far_future(raw: str) -> None:
    with pytest.raises(InvalidExpiryInputError):
        parse_expiry_date(raw)
