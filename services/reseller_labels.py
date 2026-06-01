from __future__ import annotations

import re
import secrets

from db.models import Reseller

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MIN_NAME_LEN = 2
_MAX_NAME_LEN = 32
MAX_CLIENT_EMAIL_LEN = 128


class InvalidDisplayNameError(ValueError):
    pass


class InvalidClientSuffixError(ValueError):
    pass


def normalize_display_name(raw: str) -> str:
    name = raw.strip().lower()
    if len(name) < _MIN_NAME_LEN or len(name) > _MAX_NAME_LEN:
        raise InvalidDisplayNameError(
            f"نام باید بین {_MIN_NAME_LEN} و {_MAX_NAME_LEN} کاراکتر باشد."
        )
    if not _NAME_PATTERN.match(name):
        raise InvalidDisplayNameError(
            "نام فقط می‌تواند شامل حروف انگلیسی، عدد، _ و - باشد."
        )
    return name


def reseller_label(reseller: Reseller) -> str:
    if reseller.display_name:
        return f"{reseller.display_name} ({reseller.telegram_id})"
    return str(reseller.telegram_id)


def panel_group_name(reseller: Reseller) -> str:
    """Panel client group name (e.g. ali-5266810479)."""
    if reseller.display_name:
        return f"{reseller.display_name}-{reseller.telegram_id}"
    return str(reseller.telegram_id)


def normalize_client_suffix(raw: str) -> str:
    name = raw.strip().lower()
    if len(name) < _MIN_NAME_LEN or len(name) > _MAX_NAME_LEN:
        raise InvalidClientSuffixError(
            f"نام باید بین {_MIN_NAME_LEN} و {_MAX_NAME_LEN} کاراکتر باشد."
        )
    if not _NAME_PATTERN.match(name):
        raise InvalidClientSuffixError(
            "نام فقط می‌تواند شامل حروف انگلیسی، عدد، _ و - باشد."
        )
    return name


def email_prefix(reseller: Reseller) -> str:
    if reseller.display_name:
        return reseller.display_name
    return f"r{reseller.telegram_id}"


def build_client_email(reseller: Reseller, suffix: str | None) -> str:
    resolved_suffix = secrets.token_hex(4) if suffix is None else suffix
    email = f"{email_prefix(reseller)}-client-{resolved_suffix}"
    if len(email) > MAX_CLIENT_EMAIL_LEN:
        raise InvalidClientSuffixError("نام انتخابی خیلی طولانی است.")
    return email
