import pytest

from bot.utils.panel_url import (
    InvalidPanelUrlError,
    normalize_http_url,
    normalize_sub_public_url,
)


def test_bare_host_gets_https() -> None:
    assert normalize_http_url("host:2053") == "https://host:2053"


def test_http_preserved() -> None:
    assert normalize_http_url("http://1.2.3.4:2053") == "http://1.2.3.4:2053"


def test_https_strips_trailing_slash() -> None:
    assert normalize_http_url("https://x.com/") == "https://x.com"


def test_sub_url_trailing_slash() -> None:
    assert (
        normalize_sub_public_url("sub.example.com:2096/save")
        == "https://sub.example.com:2096/save/"
    )


def test_empty_raises() -> None:
    with pytest.raises(InvalidPanelUrlError, match="خالی"):
        normalize_http_url("   ")


def test_no_host_raises() -> None:
    with pytest.raises(InvalidPanelUrlError):
        normalize_http_url("http://")
