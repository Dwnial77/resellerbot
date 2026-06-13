"""Tests for admin broadcast to resellers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramForbiddenError

from db.models import Reseller
from services.broadcast import broadcast_text_to_resellers
from xui.client import gb_to_bytes


def _reseller(tg_id: int, *, is_active: bool = True) -> Reseller:
    return Reseller(
        telegram_id=tg_id,
        panel_id=1,
        quota_bytes=gb_to_bytes(100),
        lifetime_allocated_bytes=0,
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=is_active,
    )


def test_broadcast_all_success() -> None:
    async def _run() -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=MagicMock())
        resellers = [_reseller(1), _reseller(2), _reseller(3)]
        result = await broadcast_text_to_resellers(
            bot, resellers, "hello", delay_s=0
        )
        assert result.sent == 3
        assert result.failed == 0
        assert result.blocked == 0
        assert bot.send_message.await_count == 3

    asyncio.run(_run())


def test_broadcast_counts_forbidden_as_blocked() -> None:
    async def _run() -> None:
        bot = AsyncMock()

        async def _send(chat_id: int, text: str) -> MagicMock:
            if chat_id == 2:
                raise TelegramForbiddenError(method=None, message="blocked")  # type: ignore[arg-type]
            return MagicMock()

        bot.send_message = AsyncMock(side_effect=_send)
        resellers = [_reseller(1), _reseller(2), _reseller(3)]
        result = await broadcast_text_to_resellers(
            bot, resellers, "hello", delay_s=0
        )
        assert result.sent == 2
        assert result.failed == 1
        assert result.blocked == 1

    asyncio.run(_run())


def test_broadcast_counts_other_errors_as_failed() -> None:
    async def _run() -> None:
        bot = AsyncMock()

        async def _send(chat_id: int, text: str) -> MagicMock:
            if chat_id == 2:
                raise RuntimeError("network")
            return MagicMock()

        bot.send_message = AsyncMock(side_effect=_send)
        resellers = [_reseller(1), _reseller(2)]
        result = await broadcast_text_to_resellers(
            bot, resellers, "hello", delay_s=0
        )
        assert result.sent == 1
        assert result.failed == 1
        assert result.blocked == 0

    asyncio.run(_run())


def test_broadcast_confirm_kb_callbacks() -> None:
    from bot.keyboards.common import broadcast_confirm_kb
    from bot.keyboards.labels import CANCEL, CONFIRM

    kb = broadcast_confirm_kb()
    assert kb.inline_keyboard[0][0].callback_data == "bc_confirm"
    assert kb.inline_keyboard[0][0].text == CONFIRM
    assert kb.inline_keyboard[0][1].callback_data == "bc_cancel"
    assert kb.inline_keyboard[0][1].text == CANCEL
