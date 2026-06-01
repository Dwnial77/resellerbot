from bot.utils.format_delivery import format_delivery_message
from xui.client import (
    ClientDelivery,
    VlessConfig,
    _normalize_vless_configs,
    enrich_vless_remarks_from_inbounds,
)


def test_normalize_vless_configs_from_panel_shape() -> None:
    obj = [
        {"remark": "Reality-443", "link": "vless://uuid@host:443?type=tcp"},
        {"remark": "Plain-8080", "link": "vless://uuid@host:8080?type=tcp"},
    ]
    configs = _normalize_vless_configs(obj)
    assert len(configs) == 2
    assert configs[0].remark == "Reality-443"
    assert configs[0].link.startswith("vless://")


def test_enrich_remarks_from_inbound_port() -> None:
    configs = [
        VlessConfig(
            link="vless://uuid@host:443?security=reality&type=tcp",
        ),
        VlessConfig(
            link="vless://uuid@host:8080?security=none&type=tcp",
        ),
    ]
    inbounds = [
        {"id": 1, "port": 443, "remark": "Reality-443"},
        {"id": 2, "port": 8080, "remark": "Plain-8080"},
    ]
    out = enrich_vless_remarks_from_inbounds(configs, inbounds)
    assert out[0].remark == "Reality-443"
    assert out[1].remark == "Plain-8080"


def test_enrich_uses_url_fragment_when_present() -> None:
    configs = [VlessConfig(link="vless://uuid@host:443?type=tcp#MyLabel")]
    out = enrich_vless_remarks_from_inbounds(configs, [])
    assert out[0].remark == "MyLabel"


def test_format_delivery_shows_remark() -> None:
    msg = format_delivery_message(
        "test@test",
        ClientDelivery(
            vless_configs=[
                VlessConfig(link="vless://a", remark="سرور ۱"),
            ],
        ),
        created=True,
    )
    assert "سرور ۱" in msg
    assert "vless://a" in msg
