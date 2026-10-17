"""The inline add-reseller shortcut must not swallow text typed in other flows."""

import asyncio
from datetime import datetime

from aiogram.types import Chat, Message, User

from bot.handlers import admin


def _message(text: str, user_id: int) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="x"),
        text=text,
    )


def _matches(text: str, user_id: int, raw_state: str | None) -> bool:
    handler = next(
        h for h in admin.router.message.handlers
        if h.callback is admin.add_reseller_inline
    )
    ok, _ = asyncio.run(handler.check(_message(text, user_id), raw_state=raw_state))
    return ok


def test_inline_add_ignores_text_inside_fsm_flows() -> None:
    # e.g. a card number typed in guest settings
    assert not _matches("6037 9975 1234 5678", 1, "GuestSettingsStates:card_number")


def test_inline_add_ignores_non_admins() -> None:
    assert not _matches("2500000 تومان 14", 999, None)


def test_inline_add_matches_admin_without_state() -> None:
    assert _matches("123456 50 1", 1, None)
