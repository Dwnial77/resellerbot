"""Each reseller callback must reach exactly one intended handler.

Handler order matters in aiogram (first match wins), so adding a prefix that
shadows an existing one fails silently at runtime. This pins the mapping.
"""

import asyncio
from datetime import datetime

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers.reseller import router
from bot.states import RenewServiceStates

_USER = User(id=1, is_bot=False, first_name="t")
_CHAT = Chat(id=1, type="private")
_MESSAGE = Message(message_id=1, date=datetime(2026, 1, 1), chat=_CHAT)


def _callback(data: str) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=_USER,
        chat_instance="ci",
        data=data,
        message=_MESSAGE,
    )


async def _resolve(data: str, state) -> str | None:
    ctx = FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1)
    )
    await ctx.set_state(state)
    raw = await ctx.get_state()
    for handler in router.callback_query.handlers:
        matched, _ = await handler.check(
            _callback(data), raw_state=raw, state=ctx, event_from_user=_USER
        )
        if matched:
            return handler.callback.__name__
    return None


CASES = [
    # renew flow
    ("renew:42", None, "renew_start"),
    ("rtpl:3", RenewServiceStates.pick_source, "renew_pick_template"),
    ("rman", RenewServiceStates.pick_source, "renew_manual_start"),
    ("rcfm", RenewServiceStates.confirm, "renew_confirm"),
    ("rcnl", RenewServiceStates.volume, "renew_cancel"),
    # renew buttons pressed after the FSM state is gone
    ("rtpl:3", None, "renew_stale"),
    ("rman", None, "renew_stale"),
    ("rcfm", None, "renew_stale"),
    # merged link + QR
    ("linkqr:42", None, "service_link_and_qr"),
    # edit submenu
    ("edit:42", None, "service_edit_menu"),
    ("edit_name:42", None, "service_rename_start"),
    ("edit_sub:42", None, "service_sub_regen_prompt"),
    ("sub_confirm:42", None, "service_sub_regen_confirm"),
    ("edit_back:42", None, "service_edit_back"),
    ("edit_back_menu:42", None, "service_edit_back_menu"),
    # moved under edit, callbacks unchanged
    ("traf:42", None, "add_traffic_menu"),
    ("trafd:42", None, "reduce_traffic_menu"),
    ("exp:42", None, "expiry_menu"),
    # untouched neighbours that share a prefix boundary
    ("svc:42", None, "service_detail"),
    ("traffic:42", None, "service_traffic"),
    ("del:42", None, "service_delete_prompt"),
    ("tpl:3", None, "create_from_template"),
    # `svc:` siblings must not be swallowed by the numeric detail filter
    ("svc:back", None, "services_back"),
    ("svc:pg:1", None, "services_page"),
    ("svc:search", None, "service_search_start"),
    ("svc:search:clear", None, "service_search_clear"),
]


@pytest.mark.parametrize("data,state,expected", CASES)
def test_callback_routes_to_expected_handler(data, state, expected) -> None:
    assert asyncio.run(_resolve(data, state)) == expected
