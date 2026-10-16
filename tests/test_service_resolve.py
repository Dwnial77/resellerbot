import asyncio

import pytest

from bot.utils.service_resolve import list_accessible_clients, resolve_service
from db.repository import ClientRepository
from services.panel_registry import PanelRegistry
from services.panel_resolve import ResellerInactiveError, ServiceNotFoundError
from tests.dbutil import make_session_factory, seed_reseller


def test_inactive_reseller_cannot_manage_existing_services(tmp_path) -> None:
    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as session:
            reseller = await seed_reseller(session)
            await ClientRepository(session).add(
                reseller_tg_id=100,
                panel_id=1,
                email="ali-client-a",
                inbound_ids=[1],
                allocated_bytes=1,
                expiry_time=0,
            )
            reseller.is_active = False
            await session.commit()

            registry = PanelRegistry()
            with pytest.raises(ResellerInactiveError):
                await resolve_service(session, registry, 100, "ali-client-a")
            assert await list_accessible_clients(session, registry, 100) == []
        await engine.dispose()

    asyncio.run(_run())


def test_inactive_error_is_handled_as_not_found() -> None:
    assert issubclass(ResellerInactiveError, ServiceNotFoundError)


def test_inactive_reseller_blocked_by_record_id(tmp_path) -> None:
    from bot.utils.service_resolve import resolve_service_by_id

    async def _run() -> None:
        engine, factory = await make_session_factory(tmp_path)
        async with factory() as session:
            reseller = await seed_reseller(session)
            record = await ClientRepository(session).add(
                reseller_tg_id=100, panel_id=1, email="ali-client-b",
                inbound_ids=[1], allocated_bytes=1, expiry_time=0,
            )
            reseller.is_active = False
            await session.commit()
            with pytest.raises(ResellerInactiveError):
                await resolve_service_by_id(session, PanelRegistry(), 100, record.id)
        await engine.dispose()

    asyncio.run(_run())
