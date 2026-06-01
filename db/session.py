import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import get_settings
from db.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_data_dir(url: str) -> None:
    if "sqlite" in url and "///" in url:
        path_part = url.split("///", 1)[-1]
        if path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)


def _migrate_client_records_sub_id(sync_conn) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(client_records)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "sub_id" not in columns:
        sync_conn.execute(
            text("ALTER TABLE client_records ADD COLUMN sub_id VARCHAR(64)")
        )


def _migrate_resellers_display_name(sync_conn) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(resellers)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "display_name" not in columns:
        sync_conn.execute(
            text("ALTER TABLE resellers ADD COLUMN display_name VARCHAR(64)")
        )


def _migrate_resellers_attach_inbound_ids(sync_conn) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(resellers)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "attach_inbound_ids" not in columns:
        sync_conn.execute(
            text("ALTER TABLE resellers ADD COLUMN attach_inbound_ids VARCHAR(255)")
        )
    sync_conn.execute(
        text(
            "UPDATE resellers SET attach_inbound_ids = allowed_inbound_ids "
            "WHERE attach_inbound_ids IS NULL"
        )
    )


def _seed_default_panel(sync_conn) -> int:
    count = sync_conn.execute(text("SELECT COUNT(*) FROM panels")).scalar() or 0
    if count > 0:
        return 1
    settings = get_settings()
    sync_conn.execute(
        text(
            """
            INSERT INTO panels (
                id, name, base_url, api_token, username, password,
                sub_public_url, verify_ssl, auto_vision_flow, auto_reseller_group, is_active
            ) VALUES (
                1, :name, :base_url, :api_token, :username, :password,
                :sub_public_url, :verify_ssl, :auto_vision_flow, :auto_reseller_group, 1
            )
            """
        ),
        {
            "name": "پنل پیش‌فرض",
            "base_url": settings.xui_base_url,
            "api_token": settings.xui_api_token,
            "username": settings.xui_username,
            "password": settings.xui_password,
            "sub_public_url": settings.xui_sub_public_url,
            "verify_ssl": 1 if settings.xui_verify_ssl else 0,
            "auto_vision_flow": 1 if settings.xui_auto_vision_flow else 0,
            "auto_reseller_group": 1 if settings.xui_auto_reseller_group else 0,
        },
    )
    return 1


def _migrate_resellers_panel_id(sync_conn) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(resellers)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "panel_id" not in columns:
        sync_conn.execute(
            text(
                "ALTER TABLE resellers ADD COLUMN panel_id INTEGER NOT NULL DEFAULT 1 "
                "REFERENCES panels(id)"
            )
        )
    sync_conn.execute(text("UPDATE resellers SET panel_id = 1 WHERE panel_id IS NULL"))


def _rebuild_client_records_for_panel_unique(sync_conn) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(client_records)"))
    columns = [row[1] for row in cursor.fetchall()]
    if not columns:
        return
    if "panel_id" in columns:
        indexes = sync_conn.execute(
            text("PRAGMA index_list(client_records)")
        ).fetchall()
        for idx_row in indexes:
            idx_name = idx_row[1]
            if not idx_name:
                continue
            cols = sync_conn.execute(
                text(f"PRAGMA index_info({idx_name})")
            ).fetchall()
            col_names = [c[2] for c in cols]
            if col_names == ["panel_id", "email"]:
                return
        return

    sync_conn.execute(
        text(
            """
            CREATE TABLE client_records_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reseller_tg_id BIGINT NOT NULL,
                panel_id INTEGER NOT NULL DEFAULT 1,
                email VARCHAR(128) NOT NULL,
                sub_id VARCHAR(64),
                inbound_ids VARCHAR(64) NOT NULL,
                allocated_bytes BIGINT NOT NULL,
                expiry_time BIGINT NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (panel_id, email),
                FOREIGN KEY(reseller_tg_id) REFERENCES resellers(telegram_id),
                FOREIGN KEY(panel_id) REFERENCES panels(id)
            )
            """
        )
    )
    sync_conn.execute(
        text(
            """
            INSERT INTO client_records_new (
                id, reseller_tg_id, panel_id, email, sub_id, inbound_ids,
                allocated_bytes, expiry_time, created_at
            )
            SELECT
                cr.id, cr.reseller_tg_id,
                COALESCE(r.panel_id, 1),
                cr.email, cr.sub_id, cr.inbound_ids,
                cr.allocated_bytes, cr.expiry_time, cr.created_at
            FROM client_records cr
            LEFT JOIN resellers r ON r.telegram_id = cr.reseller_tg_id
            """
        )
    )
    sync_conn.execute(text("DROP TABLE client_records"))
    sync_conn.execute(text("ALTER TABLE client_records_new RENAME TO client_records"))


def _migrate_multi_panel(sync_conn) -> None:
    _seed_default_panel(sync_conn)
    _migrate_resellers_panel_id(sync_conn)
    _rebuild_client_records_for_panel_unique(sync_conn)


async def init_db() -> None:
    global _engine, _session_factory
    settings = get_settings()
    _ensure_data_dir(settings.database_url)
    _engine = create_async_engine(settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_client_records_sub_id)
        await conn.run_sync(_migrate_resellers_display_name)
        await conn.run_sync(_migrate_resellers_attach_inbound_ids)
        await conn.run_sync(_migrate_multi_panel)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


def parse_inbound_ids(raw: str) -> list[int]:
    return json.loads(raw)
