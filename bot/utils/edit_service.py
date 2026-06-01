"""Validation helpers for reseller service edit flows."""

MAX_COMMENT_LEN = 200


class InvalidEditInputError(ValueError):
    pass


def validate_limit_ip(value: int) -> int:
    if value < 0:
        raise InvalidEditInputError("limitIp باید عدد صحیح بزرگ‌تر یا مساوی صفر باشد.")
    return value


def normalize_comment(raw: str) -> str:
    return (raw or "").strip()[:MAX_COMMENT_LEN]


def validate_comment(raw: str) -> str:
    text = normalize_comment(raw)
    if len(text) > MAX_COMMENT_LEN:
        raise InvalidEditInputError(
            f"کامنت حداکثر {MAX_COMMENT_LEN} کاراکتر می‌تواند باشد."
        )
    return text


def format_limit_ip_label(limit_ip: int) -> str:
    if limit_ip <= 0:
        return "نامحدود"
    return str(limit_ip)
