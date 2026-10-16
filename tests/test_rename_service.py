"""Tests for renaming a service and regenerating its subscription id."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from db.models import ClientRecord, Reseller
from services.reseller_service import ResellerService
from xui.client import XuiError, gb_to_bytes


def _reseller() -> Reseller:
    return Reseller(
        telegram_id=100,
        panel_id=1,
        display_name="ali",
        quota_bytes=gb_to_bytes(500),
        lifetime_allocated_bytes=0,
        allowed_inbound_ids="[1]",
        attach_inbound_ids="[1]",
        is_active=True,
    )


def _record() -> ClientRecord:
    return ClientRecord(
        id=1,
        reseller_tg_id=100,
        panel_id=1,
        email="ali-client-old",
        sub_id="oldsubid00000000",
        inbound_ids="[1]",
        allocated_bytes=gb_to_bytes(30),
        expiry_time=0,
    )


def _svc(
    *, email_taken: bool = False, panel_client: dict | None = None
) -> tuple[ResellerService, AsyncMock, AsyncMock]:
    session = AsyncMock()
    xui = AsyncMock()
    xui.get_client = AsyncMock(return_value=panel_client)
    record = _record()

    client_repo = AsyncMock()
    client_repo.session = session
    client_repo.get_for_reseller_email = AsyncMock(
        side_effect=lambda _tg, email: record if email == record.email else None
    )
    client_repo.email_exists = AsyncMock(return_value=email_taken)
    client_repo.set_email = AsyncMock(return_value=record)
    client_repo.set_sub_id = AsyncMock(return_value=record)

    svc = ResellerService(session, xui)
    svc.client_repo = client_repo
    svc.reseller_repo = AsyncMock()
    return svc, xui, client_repo


async def _rename(svc: ResellerService, reseller: Reseller, suffix: str) -> str:
    with patch(
        "services.reseller_service.UsageAlertRepository.clear",
        new_callable=AsyncMock,
    ):
        return await svc.rename_service(reseller, "ali-client-old", suffix)


def test_rename_service_updates_panel_and_db() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, client_repo = _svc()

        new_email = await _rename(svc, reseller, "new")

        assert new_email == "ali-client-new"
        xui.update_client_fields.assert_awaited_once_with(
            "ali-client-old", new_email="ali-client-new"
        )
        client_repo.set_email.assert_awaited_once()
        assert client_repo.set_email.await_args.args[1] == "ali-client-new"

    asyncio.run(_run())


def test_rename_service_keeps_reseller_prefix() -> None:
    """The suffix is all the reseller controls; the ownership prefix is fixed."""

    async def _run() -> None:
        reseller = _reseller()
        svc, _, _ = _svc()
        assert await _rename(svc, reseller, "Foo_1") == "ali-client-foo_1"

    asyncio.run(_run())


def test_rename_service_rejects_duplicate_in_db() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, _ = _svc(email_taken=True)

        with pytest.raises(XuiError, match="قبلاً استفاده شده"):
            await _rename(svc, reseller, "new")

        xui.update_client_fields.assert_not_called()

    asyncio.run(_run())


def test_rename_service_rejects_duplicate_on_panel() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, _ = _svc(panel_client={"email": "ali-client-new"})

        with pytest.raises(XuiError, match="در پنل وجود دارد"):
            await _rename(svc, reseller, "new")

        xui.update_client_fields.assert_not_called()

    asyncio.run(_run())


def test_rename_service_rejects_same_name() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, _ = _svc()

        with pytest.raises(XuiError, match="یکسان"):
            await _rename(svc, reseller, "old")

        xui.update_client_fields.assert_not_called()

    asyncio.run(_run())


def test_rename_service_rejects_invalid_suffix() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, _ = _svc()

        with pytest.raises(XuiError):
            await _rename(svc, reseller, "بد!")

        xui.update_client_fields.assert_not_called()

    asyncio.run(_run())


def test_regenerate_sub_id_sets_new_value() -> None:
    async def _run() -> None:
        reseller = _reseller()
        svc, xui, client_repo = _svc()

        new_sub = await svc.regenerate_sub_id(reseller, "ali-client-old")

        assert new_sub != "oldsubid00000000"
        assert len(new_sub) == 16
        xui.update_client_fields.assert_awaited_once_with(
            "ali-client-old", sub_id=new_sub
        )
        client_repo.set_sub_id.assert_awaited_once()
        assert client_repo.set_sub_id.await_args.args[1] == new_sub

    asyncio.run(_run())


def test_rename_service_rejects_name_used_on_another_panel() -> None:
    async def _run() -> None:
        svc, xui, client_repo = _svc()
        other = _record()
        other.id, other.panel_id, other.email = 2, 2, "ali-client-taken"
        record = await client_repo.get_for_reseller_email(100, "ali-client-old")
        client_repo.get_for_reseller_email = AsyncMock(
            side_effect=lambda _tg, email: {
                "ali-client-old": record, "ali-client-taken": other
            }.get(email)
        )
        with pytest.raises(XuiError, match="قبلاً"):
            await _rename(svc, _reseller(), "taken")
        xui.update_client_fields.assert_not_called()

    asyncio.run(_run())
