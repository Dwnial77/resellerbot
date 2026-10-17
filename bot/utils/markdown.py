"""Helpers for Telegram legacy Markdown (parse_mode="Markdown")."""


def escape_md(text: str) -> str:
    """Escape user text so _ * ` [ are shown literally."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text
