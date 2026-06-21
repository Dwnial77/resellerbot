"""Tests for database backup and restore."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from services.backup import (
    BackupError,
    apply_pending_restore,
    clear_pending_restore,
    create_backup,
    inspect_restore_file,
    list_backups,
    load_pending_restore_meta,
    pending_restore_db_path,
    save_pending_restore,
)


def _make_sqlite_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO t (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()


def _sqlite_bytes(tmp_path: Path | None = None) -> bytes:
    if tmp_path is None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
    else:
        path = tmp_path / "sample.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    raw = path.read_bytes()
    path.unlink(missing_ok=True)
    return raw


def test_inspect_restore_file_accepts_db() -> None:
    raw = _sqlite_bytes()
    out = inspect_restore_file(raw, "bot.db", max_bytes=10_000_000)
    assert out == raw


def test_inspect_restore_file_rejects_invalid() -> None:
    with pytest.raises(BackupError, match="نامعتبر"):
        inspect_restore_file(b"not a db", "bot.db", max_bytes=10_000_000)


def test_inspect_restore_file_rejects_oversize() -> None:
    raw = _sqlite_bytes()
    with pytest.raises(BackupError, match="حجم"):
        inspect_restore_file(raw, "bot.db", max_bytes=10)


def test_inspect_restore_file_accepts_zip_with_bot_db() -> None:
    db = _sqlite_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bot.db", db)
    out = inspect_restore_file(buf.getvalue(), "backup.zip", max_bytes=10_000_000)
    assert out == db


def test_inspect_restore_file_rejects_zip_without_bot_db() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.txt", b"x")
    with pytest.raises(BackupError, match="bot.db"):
        inspect_restore_file(buf.getvalue(), "backup.zip", max_bytes=10_000_000)


def test_save_and_clear_pending_restore(tmp_path: Path) -> None:
    raw = _sqlite_bytes(tmp_path)
    with patch("services.backup.get_settings") as mock_settings:
        mock_settings.return_value.database_url = (
            f"sqlite+aiosqlite:///{(tmp_path / 'data' / 'bot.db').as_posix()}"
        )
        meta = save_pending_restore(
            raw,
            uploaded_by=1,
            filename="bot.db",
            max_bytes=10_000_000,
            root=tmp_path,
        )
    assert meta.size_bytes == len(raw)
    assert pending_restore_db_path(tmp_path).is_file()
    assert load_pending_restore_meta(tmp_path) is not None
    clear_pending_restore(tmp_path)
    assert not pending_restore_db_path(tmp_path).is_file()


def test_save_pending_restore_rejects_pending_update(tmp_path: Path) -> None:
    raw = _sqlite_bytes(tmp_path)
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "pending_update.zip").write_bytes(b"zip")
    with patch("services.backup.get_settings") as mock_settings:
        mock_settings.return_value.database_url = (
            f"sqlite+aiosqlite:///{(tmp_path / 'data' / 'bot.db').as_posix()}"
        )
        with pytest.raises(BackupError, match="آپدیت"):
            save_pending_restore(
                raw,
                uploaded_by=1,
                filename="bot.db",
                max_bytes=10_000_000,
                root=tmp_path,
            )


def test_apply_pending_restore_replaces_db(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "bot.db"
    _make_sqlite_db(db_path)
    restore_db = tmp_path / "data" / "pending_restore.db"
    restore_db.parent.mkdir(parents=True, exist_ok=True)
    new_db = tmp_path / "new.db"
    _make_sqlite_db(new_db)
    conn = sqlite3.connect(str(new_db))
    try:
        conn.execute("INSERT INTO t (id) VALUES (2)")
        conn.commit()
    finally:
        conn.close()
    restore_db.write_bytes(new_db.read_bytes())
    (tmp_path / "data" / "pending_restore.json").write_text(
        '{"uploaded_by": 1, "filename": "bot.db", "size_bytes": 0}',
        encoding="utf-8",
    )

    with patch("services.backup.get_settings") as mock_settings:
        mock_settings.return_value.database_url = (
            f"sqlite+aiosqlite:///{db_path.as_posix()}"
        )
        result = apply_pending_restore(tmp_path)

    assert result is not None
    assert result.success is True
    assert not pending_restore_db_path(tmp_path).is_file()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id FROM t ORDER BY id").fetchall()
        assert rows == [(1,), (2,)]
    finally:
        conn.close()
    backups = list_backups(tmp_path)
    assert len(backups) >= 1


def test_create_backup_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "bot.db"
    _make_sqlite_db(db_path)
    with patch("services.backup.get_settings") as mock_settings:
        mock_settings.return_value.database_url = (
            f"sqlite+aiosqlite:///{db_path.as_posix()}"
        )
        path = create_backup(tmp_path)
    assert path is not None
    assert path.is_file()
    assert path.name.startswith("resellerbot-")
