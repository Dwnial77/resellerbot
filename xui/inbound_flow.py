from __future__ import annotations

import json
from typing import Any

VISION_FLOW = "xtls-rprx-vision"


def _parse_stream_settings(
    stream_settings: str | dict[str, Any] | None,
) -> tuple[str, str]:
    if stream_settings is None:
        return "", ""
    data: dict[str, Any]
    if isinstance(stream_settings, str):
        if not stream_settings.strip():
            return "", ""
        try:
            parsed = json.loads(stream_settings)
        except json.JSONDecodeError:
            return "", ""
        if not isinstance(parsed, dict):
            return "", ""
        data = parsed
    elif isinstance(stream_settings, dict):
        data = stream_settings
    else:
        return "", ""

    network = str(data.get("network", "")).lower()
    security = str(data.get("security", "")).lower()
    return network, security


def inbound_supports_vision_flow(inbound: dict[str, Any]) -> bool:
    protocol = str(inbound.get("protocol", "")).lower()
    if protocol != "vless":
        return False
    network, security = _parse_stream_settings(inbound.get("streamSettings"))
    if network != "tcp":
        return False
    return security in ("tls", "reality")


def _inbound_id(inbound: dict[str, Any]) -> int | None:
    raw = inbound.get("id", inbound.get("inboundId"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def resolve_flow_for_inbound_ids(
    inbounds: list[dict[str, Any]], inbound_ids: list[int]
) -> str:
    if not inbound_ids:
        return ""
    wanted = set(inbound_ids)
    selected = [ib for ib in inbounds if _inbound_id(ib) in wanted]
    if len(selected) != len(wanted):
        return ""
    if not selected:
        return ""
    if all(inbound_supports_vision_flow(ib) for ib in selected):
        return VISION_FLOW
    return ""
