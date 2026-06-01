import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import Reseller
from services.reseller_edit import (
    ResellerNotFoundError,
    apply_allowed_inbounds,
    apply_quota,
)


def _reseller() -> Reseller:
    return Reseller(
        telegram_id=100,
        panel_id=1,
        quota_bytes=0,
        allowed_inbound_ids="[1,2]",
        attach_inbound_ids="[1]",
    )


def test_apply_quota_success() -> None:
    async def _run() -> None:
        session = AsyncMock()
        row = _reseller()

        with patch("services.reseller_edit.ResellerRepository") as Repo:
            repo = Repo.return_value
            repo.get = AsyncMock(return_value=row)
            repo.upsert = AsyncMock(return_value=row)
            result = await apply_quota(session, 100, 50.0)

        assert "50" in result.message_text
        repo.upsert.assert_awaited_once()

    asyncio.run(_run())


def test_apply_quota_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()
        with patch("services.reseller_edit.ResellerRepository") as Repo:
            Repo.return_value.get = AsyncMock(return_value=None)
            with pytest.raises(ResellerNotFoundError):
                await apply_quota(session, 100, 10.0)

    asyncio.run(_run())


def test_apply_allowed_empty_raises() -> None:
    async def _run() -> None:
        session = AsyncMock()
        with patch("services.reseller_edit.ResellerRepository") as Repo:
            Repo.return_value.set_allowed_inbound_ids = AsyncMock(
                side_effect=ValueError("empty")
            )
            with pytest.raises(ValueError):
                await apply_allowed_inbounds(session, 100, [])

    asyncio.run(_run())
