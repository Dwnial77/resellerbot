from bot.utils.format_delivery import format_delivery_message
from xui.client import ClientDelivery, VlessConfig


def test_vless_url_with_underscores_preserved_in_message() -> None:
    link = (
        "vless://uuid@host:443?encryption=none&flow=xtls-rprx-vision"
        "&security=reality&type=tcp"
    )
    msg = format_delivery_message(
        "ali-client-test",
        ClientDelivery(vless_configs=[VlessConfig(link=link)], subscription_links=[]),
        created=True,
    )
    assert "xtls-rprx-vision" in msg
    assert "type=tcp" in msg
    assert "<code>" in msg
    assert "لینک ساب در دسترس نیست" in msg


def test_delivery_guide_with_subscription() -> None:
    msg = format_delivery_message(
        "ali-client-test",
        ClientDelivery(
            vless_configs=[VlessConfig(link="vless://a@b:1")],
            subscription_links=["https://sub.example.com/save/abc"],
        ),
        created=True,
    )
    assert "روش پیشنهادی — لینک ساب" in msg
    assert "v2rayNG" in msg
    assert "Hiddify" in msg
    assert "https://sub.example.com/save/abc" in msg


def test_delivery_guide_without_subscription() -> None:
    msg = format_delivery_message(
        "ali-client-test",
        ClientDelivery(
            vless_configs=[VlessConfig(link="vless://a@b:1")],
            subscription_links=[],
        ),
        created=True,
    )
    assert "لینک ساب در دسترس نیست" in msg
    assert "v2rayNG" not in msg


def test_delivery_shows_email_with_inbound_remark() -> None:
    email = "vispa-client-f0668410"
    msg = format_delivery_message(
        email,
        ClientDelivery(
            vless_configs=[
                VlessConfig(link="vless://a@b:443#-irancel", remark="-irancel"),
                VlessConfig(link="vless://a@b:8443#-MCI", remark="-MCI"),
            ],
            subscription_links=[],
        ),
        created=True,
    )
    assert "vispa-client-f0668410 — -irancel" in msg
    assert "vispa-client-f0668410 — -MCI" in msg
