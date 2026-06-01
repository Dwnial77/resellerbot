"""Numbered schema migrations applied once per revision."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from bot.config import get_settings

MigrationFn = Callable[[Any], None]

MIGRATIONS: list[tuple[int, MigrationFn]] = []


def _ensure_migrations_table(sync_conn: Any) -> None:
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                revision INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _is_applied(sync_conn: Any, revision: int) -> bool:
    row = sync_conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE revision = :r"),
        {"r": revision},
    ).fetchone()
    return row is not None


def _mark_applied(sync_conn: Any, revision: int) -> None:
    sync_conn.execute(
        text("INSERT INTO schema_migrations (revision) VALUES (:r)"),
        {"r": revision},
    )


def migrate_001_client_records_sub_id(sync_conn: Any) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(client_records)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "sub_id" not in columns:
        sync_conn.execute(
            text("ALTER TABLE client_records ADD COLUMN sub_id VARCHAR(64)")
        )


def migrate_002_resellers_display_name(sync_conn: Any) -> None:
    cursor = sync_conn.execute(text("PRAGMA table_info(resellers)"))
    columns = [row[1] for row in cursor.fetchall()]
    if "display_name" not in columns:
        sync_conn.execute(
            text("ALTER TABLE resellers ADD COLUMN display_name VARCHAR(64)")
        )


def migrate_003_resellers_attach_inbound_ids(sync_conn: Any) -> None:
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


def _seed_default_panel(sync_conn: Any) -> None:
    count = sync_conn.execute(text("SELECT COUNT(*) FROM panels")).scalar() or 0
    if count > 0:
        return
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


def migrate_004_resellers_panel_id(sync_conn: Any) -> None:
    _seed_default_panel(sync_conn)
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


def migrate_005_client_records_panel_unique(sync_conn: Any) -> None:
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


MIGRATIONS.extend(
    [
        (1, migrate_001_client_records_sub_id),
        (2, migrate_002_resellers_display_name),
        (3, migrate_003_resellers_attach_inbound_ids),
        (4, migrate_004_resellers_panel_id),
        (5, migrate_005_client_records_panel_unique),
    ]
)

CURRENT_SCHEMA_REVISION = max(rev for rev, _ in MIGRATIONS)


def run_pending_migrations(sync_conn: Any) -> list[int]:
    """Run migrations not yet recorded; return list of applied revision ids."""
    _ensure_migrations_table(sync_conn)
    applied: list[int] = []
    for revision, fn in MIGRATIONS:
        if _is_applied(sync_conn, revision):
            continue
        fn(sync_conn)
        _mark_applied(sync_conn, revision)
        applied.append(revision)
    return applied
