"""Database backup and restore for admin (staged apply on startup)."""

from __future__ import annotations

import io
import json
import logging
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.config import get_settings

logger = logging.getLogger(__name__)

_SQLITE_MAGIC = b"SQLite format 3\x00"
_BACKUP_GLOB = ("resellerbot-*.db", "bot.db.*")


class BackupError(Exception):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class BackupEntry:
    path: Path
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class PendingRestoreMeta:
    uploaded_by: int
    filename: str
    size_bytes: int


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    message: str
    filename: str = ""


def database_path(root: Path | None = None) -> Path:
    root = root or project_root()
    url = get_settings().database_url
    if "sqlite" not in url or "///" not in url:
        raise BackupError("فقط پایگاه داده SQLite پشتیبانی می‌شود.")
    path_part = url.split("///", 1)[-1]
    if path_part == ":memory:":
        raise BackupError("پشتیبان از دیتابیس in-memory ممکن نیست.")
    path = Path(path_part)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def backups_dir(root: Path | None = None) -> Path:
    root = root or project_root()
    d = data_dir(root) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pending_restore_db_path(root: Path | None = None) -> Path:
    return data_dir(root) / "pending_restore.db"


def pending_restore_meta_path(root: Path | None = None) -> Path:
    return data_dir(root) / "pending_restore.json"


def restore_result_path(root: Path | None = None) -> Path:
    return data_dir(root) / "restore_result.json"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sqlite_backup(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def _validate_sqlite_bytes(raw: bytes) -> None:
    if len(raw) < len(_SQLITE_MAGIC):
        raise BackupError("فایل دیتابیس نامعتبر است.")
    if not raw.startswith(_SQLITE_MAGIC):
        raise BackupError("فایل دیتابیس SQLite معتبر نیست.")


def _extract_db_from_zip(raw: bytes) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BackupError("فایل ZIP نامعتبر است.") from e
    with zf:
        matches: list[str] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            norm = info.filename.replace("\\", "/").lstrip("/")
            if ".." in norm.split("/"):
                raise BackupError("فایل ZIP نامعتبر (مسیر ناامن).")
            base = norm.rsplit("/", 1)[-1]
            if base == "bot.db":
                matches.append(norm)
        if not matches:
            raise BackupError("در ZIP فایل bot.db یافت نشد.")
        if len(matches) > 1:
            raise BackupError("ZIP باید فقط یک فایل bot.db داشته باشد.")
        return zf.read(matches[0])


def inspect_restore_file(
    raw: bytes,
    filename: str,
    *,
    max_bytes: int,
) -> bytes:
    if len(raw) > max_bytes:
        raise BackupError("حجم فایل بیش از حد مجاز است.")
    name = (filename or "").lower()
    if name.endswith(".zip"):
        db_bytes = _extract_db_from_zip(raw)
        if len(db_bytes) > max_bytes:
            raise BackupError("حجم دیتابیس داخل ZIP بیش از حد مجاز است.")
        _validate_sqlite_bytes(db_bytes)
        return db_bytes
    if name.endswith(".db") or not name:
        _validate_sqlite_bytes(raw)
        return raw
    raise BackupError("فرمت مجاز: فایل .db یا ZIP حاوی bot.db")


def create_backup(root: Path | None = None) -> Path | None:
    """Create consistent SQLite backup; returns path or None if DB missing."""
    root = root or project_root()
    src = database_path(root)
    if not src.is_file():
        return None
    dest = backups_dir(root) / f"resellerbot-{_utc_stamp()}.db"
    _sqlite_backup(src, dest)
    return dest


def create_backup_bytes(root: Path | None = None) -> tuple[bytes, str]:
    path = create_backup(root)
    if path is None:
        raise BackupError("دیتابیس یافت نشد؛ ابتدا ربات را راه‌اندازی کنید.")
    raw = path.read_bytes()
    return raw, path.name


def list_backups(root: Path | None = None) -> list[BackupEntry]:
    root = root or project_root()
    bdir = backups_dir(root)
    seen: set[Path] = set()
    entries: list[BackupEntry] = []
    for pattern in _BACKUP_GLOB:
        for path in bdir.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            stat = path.stat()
            entries.append(
                BackupEntry(
                    path=path,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
    entries.sort(key=lambda e: e.modified_at, reverse=True)
    return entries


def has_pending_update(root: Path | None = None) -> bool:
    return (data_dir(root) / "pending_update.zip").is_file()


def save_pending_restore(
    raw: bytes,
    *,
    uploaded_by: int,
    filename: str,
    max_bytes: int,
    root: Path | None = None,
) -> PendingRestoreMeta:
    root = root or project_root()
    if has_pending_update(root):
        raise BackupError("ابتدا آپدیت معلق را لغو کنید.")
    db_bytes = inspect_restore_file(raw, filename, max_bytes=max_bytes)
    pending_restore_db_path(root).write_bytes(db_bytes)
    meta = PendingRestoreMeta(
        uploaded_by=uploaded_by,
        filename=filename,
        size_bytes=len(db_bytes),
    )
    pending_restore_meta_path(root).write_text(
        json.dumps(
            {
                "uploaded_by": meta.uploaded_by,
                "filename": meta.filename,
                "size_bytes": meta.size_bytes,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return meta


def load_pending_restore_meta(root: Path | None = None) -> PendingRestoreMeta | None:
    path = pending_restore_meta_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PendingRestoreMeta(
            uploaded_by=int(data["uploaded_by"]),
            filename=str(data.get("filename", "backup.db")),
            size_bytes=int(data.get("size_bytes", 0)),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def clear_pending_restore(root: Path | None = None) -> None:
    root = root or project_root()
    for p in (pending_restore_db_path(root), pending_restore_meta_path(root)):
        if p.is_file():
            p.unlink(missing_ok=True)


def apply_pending_restore(root: Path | None = None) -> RestoreResult | None:
    root = root or project_root()
    pending = pending_restore_db_path(root)
    if not pending.is_file():
        return None
    meta = load_pending_restore_meta(root)
    filename = meta.filename if meta else pending.name
    try:
        if has_pending_update(root):
            raise BackupError("آپدیت معلق در صف است؛ ابتدا آن را لغو کنید.")
        dest = database_path(root)
        create_backup(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pending, dest)
        clear_pending_restore(root)
        result = RestoreResult(
            success=True,
            message="بازیابی دیتابیس با موفقیت انجام شد.",
            filename=filename,
        )
    except Exception as e:
        logger.exception("Pending restore failed")
        msg = str(e) if isinstance(e, BackupError) else (str(e) or "خطای ناشناخته")
        result = RestoreResult(success=False, message=msg, filename=filename)
    restore_result_path(root).write_text(
        json.dumps(
            {
                "success": result.success,
                "message": result.message,
                "filename": result.filename,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return result


def load_restore_result(root: Path | None = None) -> RestoreResult | None:
    path = restore_result_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RestoreResult(
            success=bool(data.get("success")),
            message=str(data.get("message", "")),
            filename=str(data.get("filename", "")),
        )
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        path.unlink(missing_ok=True)
