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
