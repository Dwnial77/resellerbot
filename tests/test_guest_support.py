"""Tests for the guest support-message relay."""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from bot.config import Settings
from bot.handlers.guest import support_message_received, support_start
from bot.states import GuestSupportStates


def test_support_message_received_has_rate_limit_check_param() -> None:
    params = inspect.signature(support_message_received).parameters
    assert "rate_limit_check" in params


def _settings(**overrides) -> Settings:
    base = dict(
        bot_token="t",
        admin_telegram_ids=[111, 222],
        xui_base_url="https://x",
        guest_order_rate_limit=3,
    )
    base.update(overrides)
    return Settings(**base)


def test_support_start_sets_state_and_prompts() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()
        state = AsyncMock()

        await support_start(message, state)

        state.set_state.assert_awaited_once_with(GuestSupportStates.message)
        message.answer.assert_awaited_once()

    asyncio.run(_run())


def test_support_message_received_forwards_text_to_all_admins() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 42
        message.from_user.username = "buyer"
        message.text = "کانفیگم وصل نمیشه"
        message.caption = None
        message.photo = None
        message.answer = AsyncMock()
        message.bot.send_message = AsyncMock()
        message.bot.send_photo = AsyncMock()

        state = AsyncMock()
        rate_limit_check = MagicMock(return_value=True)

        with patch("bot.handlers.guest.get_settings", return_value=_settings()):
            await support_message_received(message, state, rate_limit_check)

        rate_limit_check.assert_called_once_with(42, 3)
        assert message.bot.send_message.await_count == 2
        sent_to = {c.args[0] for c in message.bot.send_message.await_args_list}
        assert sent_to == {111, 222}
        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()

    asyncio.run(_run())


def test_support_message_received_forwards_photo_with_caption() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 42
        message.from_user.username = None
        message.text = None
        message.caption = None
        photo_size = MagicMock()
        photo_size.file_id = "file123"
        message.photo = [photo_size]
        message.answer = AsyncMock()
        message.bot.send_message = AsyncMock()
        message.bot.send_photo = AsyncMock()

        state = AsyncMock()
        rate_limit_check = MagicMock(return_value=True)

        with patch("bot.handlers.guest.get_settings", return_value=_settings()):
            await support_message_received(message, state, rate_limit_check)

        assert message.bot.send_photo.await_count == 2
        message.bot.send_message.assert_not_awaited()

    asyncio.run(_run())


def test_support_message_received_respects_rate_limit() -> None:
    async def _run() -> None:
        message = MagicMock()
        message.from_user.id = 42
        message.text = "help"
        message.caption = None
        message.photo = None
        message.answer = AsyncMock()
        message.bot.send_message = AsyncMock()

        state = AsyncMock()
        rate_limit_check = MagicMock(return_value=False)

        with patch("bot.handlers.guest.get_settings", return_value=_settings()):
            await support_message_received(message, state, rate_limit_check)

        message.bot.send_message.assert_not_awaited()
        state.clear.assert_not_awaited()

    asyncio.run(_run())
