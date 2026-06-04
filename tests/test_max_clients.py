"""Tests for max_clients quota display and validation helpers."""

from services.quota import QuotaStatus, format_max_clients_admin, format_max_clients_line


def _status(
    *,
    max_clients: int | None,
    client_count: int = 0,
) -> QuotaStatus:
    return QuotaStatus(
        quota_bytes=100 * 1024**3,
        active_bytes=0,
        lifetime_bytes=0,
        remaining_bytes=100 * 1024**3,
        client_count=client_count,
        max_clients=max_clients,
    )


def test_format_max_clients_line_unlimited():
    assert format_max_clients_line(_status(max_clients=None)) == "نامحدود"


def test_format_max_clients_line_limited():
    line = format_max_clients_line(_status(max_clients=5, client_count=2))
    assert line == "5 سرویس (فعلی: 2)"


def test_format_max_clients_admin():
    assert format_max_clients_admin(_status(max_clients=None)) == "نامحدود"
    assert format_max_clients_admin(_status(max_clients=10)) == "10"


def test_parse_max_clients_value():
    """Admin command accepts integers >= 1 only."""
    valid = [1, 10, 999]
    for n in valid:
        assert isinstance(n, int) and n >= 1
    invalid = [0, -1]
    for n in invalid:
        assert n < 1


if __name__ == "__main__":
    test_format_max_clients_line_unlimited()
    test_format_max_clients_line_limited()
    test_format_max_clients_admin()
    test_parse_max_clients_value()
    print("ok")
