"""Tests for the admin 'preview guest mode' button."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers.admin_guest_settings import preview_guest_mode
from bot.keyboards import labels as L


def test_preview_guest_mode_sends_guest_keyboard() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 999
        message.answer = AsyncMock()

        with patch("bot.handlers.admin_guest_settings._is_admin", return_value=True):
            await preview_guest_mode(message)

        message.answer.assert_awaited_once()
        _, kwargs = message.answer.await_args
        markup = kwargs["reply_markup"]
        button_texts = {b.text for row in markup.keyboard for b in row}
        assert L.BUY_ACCOUNT in button_texts
        assert L.MY_ORDERS in button_texts
        assert L.SUPPORT in button_texts

    asyncio.run(_run())


def test_preview_guest_mode_rejects_non_admin() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 111
        message.answer = AsyncMock()

        with patch("bot.handlers.admin_guest_settings._is_admin", return_value=False):
            await preview_guest_mode(message)

        message.answer.assert_not_awaited()

    asyncio.run(_run())
