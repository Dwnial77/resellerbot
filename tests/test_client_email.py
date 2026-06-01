from db.models import Reseller
from services.reseller_labels import (
    InvalidClientSuffixError,
    MAX_CLIENT_EMAIL_LEN,
    build_client_email,
    normalize_client_suffix,
)


def _reseller(display_name: str | None = None, tg_id: int = 5266810479) -> Reseller:
    return Reseller(
        telegram_id=tg_id,
        display_name=display_name,
        quota_bytes=0,
        allowed_inbound_ids="[1]",
    )


def test_build_client_email_with_display_name() -> None:
    email = build_client_email(_reseller("ali"), "myvpn")
    assert email == "ali-client-myvpn"


def test_build_client_email_without_display_name() -> None:
    email = build_client_email(_reseller(None, 123), "test")
    assert email == "r123-client-test"


def test_build_client_email_random_suffix() -> None:
    email = build_client_email(_reseller("ali"), None)
    assert email.startswith("ali-client-")
    assert len(email.split("-")[-1]) == 8


def test_normalize_client_suffix_rejects_short() -> None:
    try:
        normalize_client_suffix("a")
        raise AssertionError("expected InvalidClientSuffixError")
    except InvalidClientSuffixError:
        pass


def test_build_client_email_max_length() -> None:
    long_suffix = "x" * 41
    try:
        build_client_email(_reseller("a" * 80), long_suffix)
        raise AssertionError("expected InvalidClientSuffixError")
    except InvalidClientSuffixError:
        pass
    assert MAX_CLIENT_EMAIL_LEN == 128
