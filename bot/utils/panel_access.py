"""Reseller panel access helpers for Telegram handlers."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from bot.texts import fa as t
from db.models import Reseller
from db.session import get_session_factory
from services.panel_registry import PanelRegistry
from services.panel_resolve import (
    ResellerPanelReason,
    ResellerPanelUnavailableError,
    xui_for_reseller,
)
from xui.client import XuiClient


def format_reseller_panel_unavailable(exc: ResellerPanelUnavailableError) -> str:
    name = exc.panel_name or f"#{exc.panel_id}"
    if exc.reason == ResellerPanelReason.INACTIVE:
        return t.RESELLER_PANEL_INACTIVE.format(
            panel_name=name, panel_id=exc.panel_id
        )
    if exc.reason == ResellerPanelReason.MISSING:
        return t.RESELLER_PANEL_MISSING.format(panel_id=exc.panel_id)
    return t.RESELLER_PANEL_NOT_LOADED.format(
        panel_name=name, panel_id=exc.panel_id
    )


async def answer_panel_unavailable(
    target: Message | CallbackQuery, exc: ResellerPanelUnavailableError
) -> None:
    text = format_reseller_panel_unavailable(exc)
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await target.answer(text)


async def resolve_reseller_xui(
    registry: PanelRegistry,
    reseller: Reseller,
) -> XuiClient:
    async with get_session_factory()() as session:
        return await xui_for_reseller(registry, session, reseller)


async def ensure_reseller_panel_access(
    target: Message | CallbackQuery,
    registry: PanelRegistry,
    reseller: Reseller,
) -> XuiClient | None:
    try:
        return await resolve_reseller_xui(registry, reseller)
    except ResellerPanelUnavailableError as e:
        await answer_panel_unavailable(target, e)
        return None
