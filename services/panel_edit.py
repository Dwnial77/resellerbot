"""Admin operations for editing 3x-ui panel connection settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import fa as t
from db.models import Panel
from db.repository import PanelRepository
from xui.client import XuiClient


class PanelNotFoundError(LookupError):
    pass


class PanelConnectionError(Exception):
    """Panel API authentication failed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class PanelEditResult:
    panel: Panel
    message_text: str


async def _get_panel(session: AsyncSession, panel_id: int) -> Panel:
    row = await PanelRepository(session).get(panel_id)
    if not row:
        raise PanelNotFoundError()
    return row


async def _test_panel_connection(
    panel: Panel,
    *,
    base_url: str | None = None,
    api_token: str | None = None,
    sub_public_url: str | None = None,
) -> None:
    client = XuiClient(
        base_url or panel.base_url,
        api_token=api_token if api_token is not None else panel.api_token,
        username=panel.username,
        password=panel.password,
        verify_ssl=panel.verify_ssl,
        sub_public_url=(
            sub_public_url
            if sub_public_url is not None
            else panel.sub_public_url
        ),
        auto_vision_flow=panel.auto_vision_flow,
        auto_reseller_group=panel.auto_reseller_group,
    )
    try:
        await client.ensure_authenticated()
    except Exception as e:
        raise PanelConnectionError(str(e)[:200]) from e
    finally:
        await client.close()


async def apply_panel_name(
    session: AsyncSession, panel_id: int, name: str
) -> PanelEditResult:
    repo = PanelRepository(session)
    try:
        row = await repo.update_name(panel_id, name)
    except ValueError as e:
        raise ValueError(str(e)) from e
    if not row:
        raise PanelNotFoundError()
    return PanelEditResult(
        panel=row,
        message_text=t.PANEL_NAME_UPDATED.format(id=row.id, name=row.name),
    )


async def apply_panel_base_url(
    session: AsyncSession, panel_id: int, base_url: str
) -> PanelEditResult:
    panel = await _get_panel(session, panel_id)
    from bot.utils.panel_url import normalize_http_url

    normalized = normalize_http_url(base_url)
    await _test_panel_connection(panel, base_url=normalized)
    row = await PanelRepository(session).update_base_url(panel_id, normalized)
    assert row is not None
    return PanelEditResult(
        panel=row,
        message_text=t.PANEL_URL_UPDATED.format(
            id=row.id, name=row.name, base_url=row.base_url
        ),
    )


async def apply_panel_api_token(
    session: AsyncSession, panel_id: int, api_token: str
) -> PanelEditResult:
    panel = await _get_panel(session, panel_id)
    token = api_token.strip()
    if not token:
        raise ValueError("توکن API نمی‌تواند خالی باشد.")
    await _test_panel_connection(panel, api_token=token)
    row = await PanelRepository(session).update_api_token(panel_id, token)
    assert row is not None
    return PanelEditResult(
        panel=row,
        message_text=t.PANEL_TOKEN_UPDATED.format(id=row.id, name=row.name),
    )


async def apply_panel_sub_public_url(
    session: AsyncSession, panel_id: int, sub_public_url: str | None
) -> PanelEditResult:
    row = await PanelRepository(session).update_sub_public_url(
        panel_id, sub_public_url
    )
    if not row:
        raise PanelNotFoundError()
    sub = row.sub_public_url or "—"
    return PanelEditResult(
        panel=row,
        message_text=t.PANEL_SUB_UPDATED.format(
            id=row.id, name=row.name, sub_public_url=sub
        ),
    )
