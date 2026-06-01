import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import Reseller
from db.repository import ResellerRepository


def _reseller(tg_id: int = 100) -> Reseller:
    return Reseller(
        telegram_id=tg_id,
        panel_id=1,
        quota_bytes=0,
        allowed_inbound_ids="[1]",
    )


def test_delete_success_zero_clients() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller()

        with patch.object(ResellerRepository, "get", AsyncMock(return_value=reseller)):
            with patch.object(
                ResellerRepository, "client_count", AsyncMock(return_value=0)
            ):
                repo = ResellerRepository(session)
                ok = await repo.delete(100)

        assert ok is True
        session.execute.assert_awaited_once()
        session.delete.assert_called_once_with(reseller)
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_delete_blocked_when_has_clients() -> None:
    async def _run() -> None:
        session = AsyncMock()
        reseller = _reseller()

        with patch.object(ResellerRepository, "get", AsyncMock(return_value=reseller)):
            with patch.object(
                ResellerRepository, "client_count", AsyncMock(return_value=2)
            ):
                repo = ResellerRepository(session)
                with pytest.raises(ValueError, match="سرویس"):
                    await repo.delete(100)

        session.delete.assert_not_called()

    asyncio.run(_run())


def test_delete_not_found() -> None:
    async def _run() -> None:
        session = AsyncMock()

        with patch.object(ResellerRepository, "get", AsyncMock(return_value=None)):
            repo = ResellerRepository(session)
            ok = await repo.delete(999)

        assert ok is False

    asyncio.run(_run())
