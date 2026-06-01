import pytest

from bot.utils.qr_vless import (
    InvalidVlessQrError,
    generate_vless_qr_png,
    is_vless_config_url,
)


def test_is_vless_config_url() -> None:
    assert is_vless_config_url("vless://uuid@host:443?type=tcp")
    assert not is_vless_config_url("https://sub.example.com/save/abc")


def test_generate_vless_qr_png() -> None:
    link = "vless://uuid@host:443?encryption=none&type=tcp#test"
    png = generate_vless_qr_png(link)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 500


def test_reject_subscription_url() -> None:
    with pytest.raises(InvalidVlessQrError):
        generate_vless_qr_png("https://example.com/sub/id")
