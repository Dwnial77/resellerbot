"""Resolve reseller service context (record + panel XUI) for handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from db.models import ClientRecord, Reseller
from db.repository import ClientRepository, ResellerRepository
from db.session import get_session_factory
from services.panel_registry import PanelRegistry
from services.panel_resolve import (
    ServiceNotFoundError,
    ServicePanelUnavailableError,
    list_accessible_panel_ids,
    xui_for_record,
)
from xui.client import XuiClient


@dataclass(frozen=True)
class ServiceContext:
    reseller: Reseller
    record: ClientRecord
    xui: XuiClient


async def resolve_service(
    session: AsyncSession,
    registry: PanelRegistry,
    user_id: int,
    email: str,
) -> ServiceContext:
    reseller = await ResellerRepository(session).get(user_id)
    if not reseller:
        raise ServiceNotFoundError()
    record = await ClientRepository(session).get_for_reseller_email(user_id, email)
    if not record:
        raise ServiceNotFoundError()
    xui = xui_for_record(registry, record)
    return ServiceContext(reseller=reseller, record=record, xui=xui)


async def list_accessible_clients(
    session: AsyncSession,
    registry: PanelRegistry,
    reseller_tg_id: int,
) -> list[ClientRecord]:
    panel_ids = list_accessible_panel_ids(registry)
    return await ClientRepository(session).list_for_reseller_on_panels(
        reseller_tg_id, panel_ids
    )


async def answer_resolve_callback(
    callback: CallbackQuery, exc: BaseException
) -> None:
    if isinstance(exc, ServiceNotFoundError):
        await callback.answer(t.SERVICE_NOT_FOUND, show_alert=True)
    elif isinstance(exc, ServicePanelUnavailableError):
        await callback.answer(
            t.SERVICE_PANEL_UNAVAILABLE.format(panel_id=exc.panel_id),
            show_alert=True,
        )
    else:
        raise exc


async def answer_resolve_message(message: Message, exc: BaseException) -> None:
    if isinstance(exc, ServiceNotFoundError):
        await message.answer(t.SERVICE_NOT_FOUND)
    elif isinstance(exc, ServicePanelUnavailableError):
        await message.answer(
            t.SERVICE_PANEL_UNAVAILABLE.format(panel_id=exc.panel_id)
        )
    else:
        raise exc


@asynccontextmanager
async def open_service_context(
    registry: PanelRegistry,
    user_id: int,
    email: str,
) -> AsyncIterator[tuple[ServiceContext, AsyncSession]]:
    async with get_session_factory()() as session:
        ctx = await resolve_service(session, registry, user_id, email)
        yield ctx, session
