"""Manual-volume buttons of the add/reduce traffic dialogs (state holds record_id)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.reseller import add_traffic_custom_start, reduce_traffic_custom_start
from bot.states import AddTrafficStates, ReduceTrafficStates


@pytest.mark.parametrize(
    "handler,expected",
    [
        (add_traffic_custom_start, AddTrafficStates.volume),
        (reduce_traffic_custom_start, ReduceTrafficStates.volume),
    ],
)
def test_manual_entry_moves_to_volume_state(handler, expected) -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"record_id": 5})
    callback = MagicMock()
    callback.message = AsyncMock()
    callback.answer = AsyncMock()
    asyncio.run(handler(callback, state))
    state.set_state.assert_awaited_once_with(expected)
    callback.message.edit_text.assert_awaited_once()
