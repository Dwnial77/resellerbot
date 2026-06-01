"""Generate QR PNG images for VLESS/VMess config URLs (not subscription links)."""

from __future__ import annotations

import io

import qrcode
from qrcode.constants import ERROR_CORRECT_H

_VLESS_PREFIXES = ("vless://", "vmess://", "trojan://", "ss://")


class InvalidVlessQrError(ValueError):
    pass


def is_vless_config_url(link: str) -> bool:
    text = (link or "").strip()
    return text.startswith(_VLESS_PREFIXES)


def generate_vless_qr_png(link: str) -> bytes:
    text = (link or "").strip()
    if not is_vless_config_url(text):
        raise InvalidVlessQrError("فقط لینک کانفیگ VLESS/VMess برای QR مجاز است.")
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
