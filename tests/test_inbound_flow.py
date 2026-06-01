from xui.inbound_flow import (
    VISION_FLOW,
    inbound_supports_vision_flow,
    resolve_flow_for_inbound_ids,
)


def _inbound(
    inbound_id: int,
    protocol: str,
    network: str,
    security: str,
) -> dict:
    return {
        "id": inbound_id,
        "protocol": protocol,
        "streamSettings": f'{{"network":"{network}","security":"{security}"}}',
    }


def test_vless_tcp_reality_supports_vision() -> None:
    ib = _inbound(1, "vless", "tcp", "reality")
    assert inbound_supports_vision_flow(ib) is True


def test_vless_xhttp_reality_not_supported() -> None:
    ib = _inbound(1, "vless", "xhttp", "reality")
    assert inbound_supports_vision_flow(ib) is False


def test_vless_tcp_none_not_supported() -> None:
    ib = _inbound(1, "vless", "tcp", "none")
    assert inbound_supports_vision_flow(ib) is False


def test_resolve_all_vision_inbounds() -> None:
    inbounds = [
        _inbound(1, "vless", "tcp", "reality"),
        _inbound(2, "vless", "tcp", "tls"),
    ]
    assert resolve_flow_for_inbound_ids(inbounds, [1, 2]) == VISION_FLOW


def test_resolve_mixed_inbounds_empty_flow() -> None:
    inbounds = [
        _inbound(1, "vless", "tcp", "reality"),
        _inbound(2, "vless", "xhttp", "reality"),
    ]
    assert resolve_flow_for_inbound_ids(inbounds, [1, 2]) == ""


def test_resolve_missing_inbound_empty_flow() -> None:
    inbounds = [_inbound(1, "vless", "tcp", "reality")]
    assert resolve_flow_for_inbound_ids(inbounds, [1, 99]) == ""
