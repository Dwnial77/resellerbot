"""Panel-style VLESS URL fragment (#remark) matching 3x-ui SubService.genRemark (-e model)."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit, urlunsplit


def format_traffic_bytes(value: int) -> str:
    """Approximate 3x-ui common.FormatTraffic for positive totals (e.g. 10.00GB)."""
    if value <= 0:
        return "0B"
    units = [
        (1024**4, "TB"),
        (1024**3, "GB"),
        (1024**2, "MB"),
        (1024, "KB"),
    ]
    for size, suffix in units:
        if value >= size:
            amount = value / size
            if suffix == "GB":
                return f"{amount:.2f}{suffix}"
            if amount >= 100:
                return f"{amount:.0f}{suffix}"
            if amount >= 10:
                return f"{amount:.1f}{suffix}"
            return f"{amount:.2f}{suffix}"
    return f"{value}B"


def build_panel_link_fragment(email: str, total_bytes: int) -> str:
    """Default panel remark model `-e`: email + total traffic + chart emoji."""
    volume = format_traffic_bytes(total_bytes)
    return f"{email}-{volume}📊"


def apply_fragment_to_vless_link(link: str, fragment_text: str) -> str:
    if not fragment_text.strip():
        return link
    parts = urlsplit(link)
    if parts.fragment:
        return link
    encoded = quote(fragment_text, safe="")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, encoded))


def decode_link_fragment(link: str) -> str:
    parts = urlsplit(link)
    if not parts.fragment:
        return ""
    return unquote(parts.fragment)
