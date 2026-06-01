"""Normalize panel and subscription base URLs for admin input."""

from __future__ import annotations

from urllib.parse import urlparse


class InvalidPanelUrlError(ValueError):
    """User-entered URL could not be normalized."""


def normalize_http_url(raw: str, *, default_scheme: str = "https") -> str:
    """
    Accept http(s) URLs or bare host:port; default scheme is https when omitted.
    Strips whitespace and trailing slashes on the path root.
    """
    value = (raw or "").strip()
    if not value:
        raise InvalidPanelUrlError(
            "آدرس نمی‌تواند خالی باشد. مثال: host:2053 یا https://host:2053"
        )

    if "://" not in value:
        value = f"{default_scheme}://{value}"

    value = value.rstrip("/")

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise InvalidPanelUrlError(
            "فقط http یا https پشتیبانی می‌شود. مثال: http://host:2053"
        )
    if not parsed.netloc:
        raise InvalidPanelUrlError(
            "آدرس نامعتبر است. مثال: host:2053 یا https://host:2053"
        )

    return value


def normalize_sub_public_url(raw: str, *, default_scheme: str = "https") -> str:
    """Like normalize_http_url but ensures a trailing slash for sub path joining."""
    url = normalize_http_url(raw, default_scheme=default_scheme)
    return url if url.endswith("/") else f"{url}/"
