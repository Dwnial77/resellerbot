"""Apply release ZIP updates on startup; stage uploads from admin."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bot.version import __version__ as RUNNING_VERSION

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Paths never overwritten from release ZIP
_PROTECTED_NAMES = frozenset({".env", ".venv", "data", "dist", ".git"})

# Top-level entries copied from release archive
_RELEASE_ROOT_ENTRIES = frozenset(
    {
        "bot",
        "db",
        "services",
        "xui",
        "deploy",
        "scripts",
        "requirements.txt",
        "RELEASE.json",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
    }
)

_REQUIRED_IN_ZIP = ("bot/version.py",)


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class PendingUpdateMeta:
    target_version: str
    uploaded_by: int
    filename: str


@dataclass(frozen=True)
class UpdateResult:
    success: bool
    previous_version: str
    new_version: str
    message: str


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pending_zip_path(root: Path | None = None) -> Path:
    return data_dir(root) / "pending_update.zip"


def pending_meta_path(root: Path | None = None) -> Path:
    return data_dir(root) / "pending_update.json"


def update_result_path(root: Path | None = None) -> Path:
    return data_dir(root) / "update_result.json"


def parse_version(raw: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(raw.strip())
    if not m:
        raise UpdateError(f"نسخه نامعتبر: {raw}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def compare_versions(a: str, b: str) -> int:
    """Return negative if a < b, 0 if equal, positive if a > b."""
    ta, tb = parse_version(a), parse_version(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def read_version_from_tree(root: Path) -> str:
    release_json = root / "RELEASE.json"
    if release_json.is_file():
        try:
            data = json.loads(release_json.read_text(encoding="utf-8"))
            ver = data.get("version")
            if isinstance(ver, str) and ver.strip():
                return ver.strip()
        except (json.JSONDecodeError, OSError):
            pass
    version_py = root / "bot" / "version.py"
    if not version_py.is_file():
        raise UpdateError("bot/version.py در بسته یافت نشد.")
    text = version_py.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("__version__"):
            part = line.split("=", 1)[1].strip().strip('"').strip("'")
            return part
    raise UpdateError("نسخه در bot/version.py یافت نشد.")


def _safe_extract(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise UpdateError("فایل ZIP نامعتبر (مسیر ناامن).")
        zf.extractall(dest)
    # GitHub source zip has one top-level folder
    children = [p for p in dest.iterdir() if p.name not in ("__MACOSX",)]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return dest


def _validate_release_tree(tree: Path) -> str:
    for req in _REQUIRED_IN_ZIP:
        if not (tree / req).is_file():
            raise UpdateError(f"فایل الزامی در ZIP نیست: {req}")
    return read_version_from_tree(tree)


def inspect_release_zip(
    zip_path: Path,
    *,
    current_version: str = RUNNING_VERSION,
    allow_downgrade: bool = False,
) -> str:
    if not zip_path.is_file():
        raise UpdateError("فایل ZIP یافت نشد.")
    staging = data_dir() / "inspect_update"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        tree = _safe_extract(zip_path, staging)
        target = _validate_release_tree(tree)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    cmp = compare_versions(target, current_version)
    if cmp < 0 and not allow_downgrade:
        raise UpdateError(
            f"نسخه ZIP ({target}) قدیمی‌تر از نسخه فعلی ({current_version}) است."
        )
    if cmp == 0:
        raise UpdateError(f"نسخه ZIP همان نسخه فعلی ({current_version}) است.")
    return target


def save_pending_update(
    zip_bytes: bytes,
    *,
    uploaded_by: int,
    filename: str,
    max_bytes: int,
    allow_downgrade: bool = False,
    root: Path | None = None,
) -> PendingUpdateMeta:
    if len(zip_bytes) > max_bytes:
        raise UpdateError("حجم فایل ZIP بیش از حد مجاز است.")
    root = root or project_root()
    zip_path = pending_zip_path(root)
    zip_path.write_bytes(zip_bytes)
    target = inspect_release_zip(
        zip_path, allow_downgrade=allow_downgrade
    )
    meta = PendingUpdateMeta(
        target_version=target,
        uploaded_by=uploaded_by,
        filename=filename,
    )
    pending_meta_path(root).write_text(
        json.dumps(
            {
                "target_version": meta.target_version,
                "uploaded_by": meta.uploaded_by,
                "filename": meta.filename,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return meta


def load_pending_meta(root: Path | None = None) -> PendingUpdateMeta | None:
    path = pending_meta_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PendingUpdateMeta(
            target_version=str(data["target_version"]),
            uploaded_by=int(data["uploaded_by"]),
            filename=str(data.get("filename", "update.zip")),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def clear_pending(root: Path | None = None) -> None:
    root = root or project_root()
    for p in (pending_zip_path(root), pending_meta_path(root)):
        if p.is_file():
            p.unlink(missing_ok=True)


def _backup_database(root: Path) -> None:
    db_file = root / "data" / "bot.db"
    if not db_file.is_file():
        return
    backups = root / "data" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(db_file, backups / f"bot.db.{stamp}")


def _copy_release_into_install(tree: Path, install: Path) -> None:
    for name in _RELEASE_ROOT_ENTRIES:
        src = tree / name
        if not src.exists():
            continue
        dst = install / name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _run_pip_install(install: Path) -> None:
    req = install / "requirements.txt"
    if not req.is_file():
        return
    venv_python = install / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        venv_python = install / ".venv" / "Scripts" / "python.exe"
    python = str(venv_python) if venv_python.is_file() else sys.executable
    subprocess.run(
        [python, "-m", "pip", "install", "-r", str(req)],
        cwd=str(install),
        check=True,
        timeout=600,
    )


def apply_pending_update(
    root: Path | None = None,
    *,
    allow_downgrade: bool = False,
) -> UpdateResult | None:
    root = root or project_root()
    zip_path = pending_zip_path(root)
    if not zip_path.is_file():
        return None
    previous = RUNNING_VERSION
    staging = data_dir(root) / "staging_update"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    target = previous
    try:
        tree = _safe_extract(zip_path, staging)
        target = _validate_release_tree(tree)
        if compare_versions(target, previous) < 0 and not allow_downgrade:
            raise UpdateError("downgrade blocked")
        _backup_database(root)
        _copy_release_into_install(tree, root)
        _run_pip_install(root)
        clear_pending(root)
        result = UpdateResult(
            success=True,
            previous_version=previous,
            new_version=target,
            message=f"به‌روزرسانی {previous} → {target} اعمال شد.",
        )
    except Exception as e:
        logger.exception("Pending update failed")
        result = UpdateResult(
            success=False,
            previous_version=previous,
            new_version=target,
            message=str(e) if isinstance(e, UpdateError) else (str(e) or "خطای ناشناخته"),
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    update_result_path(root).write_text(
        json.dumps(
            {
                "success": result.success,
                "previous_version": result.previous_version,
                "new_version": result.new_version,
                "message": result.message,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return result


def load_update_result(root: Path | None = None) -> UpdateResult | None:
    path = update_result_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return UpdateResult(
            success=bool(data.get("success")),
            previous_version=str(data.get("previous_version", "")),
            new_version=str(data.get("new_version", "")),
            message=str(data.get("message", "")),
        )
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        path.unlink(missing_ok=True)


def request_service_restart(service_name: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["sudo", "-n", "systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, "ری‌استارت سرویس درخواست شد."
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err or f"systemctl exit {proc.returncode}"
    except FileNotFoundError:
        return False, "sudo یا systemctl یافت نشد."
    except subprocess.TimeoutExpired:
        return False, "ری‌استارت زمان‌دار شد."
