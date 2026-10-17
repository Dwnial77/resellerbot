"""Record ids are guessable, so ownership must be enforced in the query itself."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Base, ClientRecord, Panel, Reseller
from db.repository import ClientRepository
from xui.client import gb_to_bytes


async def _seed(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Panel(id=1, name="p1", base_url="https://x", verify_ssl=False))
        for tg_id in (100, 200):
            session.add(
                Reseller(
                    telegram_id=tg_id,
                    panel_id=1,
                    quota_bytes=gb_to_bytes(100),
                    allowed_inbound_ids="[1]",
                    attach_inbound_ids="[1]",
                )
            )
        await session.commit()
        owned = ClientRecord(
            reseller_tg_id=100,
            panel_id=1,
            email="ali-client-a",
            inbound_ids="[1]",
            allocated_bytes=gb_to_bytes(20),
        )
        session.add(owned)
        await session.commit()
        await session.refresh(owned)
        return factory, owned.id


def test_owner_can_fetch_own_record() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            factory, record_id = await _seed(engine)
            async with factory() as session:
                record = await ClientRepository(session).get_for_reseller_id(
                    100, record_id
                )
            assert record is not None
            assert record.email == "ali-client-a"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_other_reseller_cannot_fetch_record_by_id() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            factory, record_id = await _seed(engine)
            async with factory() as session:
                record = await ClientRepository(session).get_for_reseller_id(
                    200, record_id
                )
            assert record is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_unknown_id_returns_none() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            factory, record_id = await _seed(engine)
            async with factory() as session:
                record = await ClientRepository(session).get_for_reseller_id(
                    100, record_id + 9999
                )
            assert record is None
        finally:
            await engine.dispose()

    asyncio.run(_run())
