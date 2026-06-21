"""Apply release ZIP updates on startup; stage uploads from admin."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from bot.version import __version__ as RUNNING_VERSION
from services.backup import create_backup

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
_BOT_VERSION_REL = "bot/version.py"
_MAX_RELEASE_ROOT_DEPTH = 4


class UpdateError(Exception):
    pass


def _normalize_zip_path(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def _has_required_files(root: Path) -> bool:
    return all((root / req).is_file() for req in _REQUIRED_IN_ZIP)


def _zip_entry_sample(zip_path: Path, limit: int = 8) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [
            _normalize_zip_path(info.filename)
            for info in zf.infolist()
            if not info.is_dir()
        ][:limit]
    if not names:
        return "(ZIP خالی)"
    return ", ".join(names)


def _missing_version_error(zip_path: Path) -> UpdateError:
    return UpdateError(
        "فایل الزامی در ZIP نیست: bot/version.py\n"
        f"نمونه مسیرهای داخل ZIP: {_zip_entry_sample(zip_path)}"
    )


def _is_bot_version_path(path: str) -> bool:
    return path == _BOT_VERSION_REL or path.endswith(f"/{_BOT_VERSION_REL}")


def _find_bot_version_path_in_zip(zf: zipfile.ZipFile, zip_path: Path) -> str:
    matches = [
        _normalize_zip_path(info.filename)
        for info in zf.infolist()
        if not info.is_dir() and _is_bot_version_path(_normalize_zip_path(info.filename))
    ]
    if not matches:
        raise _missing_version_error(zip_path)
    return sorted(matches)[0]


def _release_prefix_from_version_path(version_path: str) -> str:
    if version_path == _BOT_VERSION_REL:
        return ""
    suffix = f"/{_BOT_VERSION_REL}"
    if version_path.endswith(suffix):
        return version_path[: -len(suffix)] + "/"
    return ""


def _parse_version_from_text(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("__version__"):
            part = line.split("=", 1)[1].strip().strip('"').strip("'")
            return part
    raise UpdateError("نسخه در bot/version.py یافت نشد.")


def read_version_from_zip(zip_path: Path) -> str:
    """Read target version from ZIP members without extracting."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        version_path = _find_bot_version_path_in_zip(zf, zip_path)
        prefix = _release_prefix_from_version_path(version_path)
        release_key = f"{prefix}RELEASE.json" if prefix else "RELEASE.json"
        names = {_normalize_zip_path(i.filename) for i in zf.infolist() if not i.is_dir()}
        if release_key in names:
            try:
                data = json.loads(zf.read(release_key).decode("utf-8"))
                ver = data.get("version")
                if isinstance(ver, str) and ver.strip():
                    return ver.strip()
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                pass
        text = zf.read(version_path).decode("utf-8")
        return _parse_version_from_text(text)


def find_release_root(tree: Path, *, zip_path: Path | None = None) -> Path:
    """Locate release root containing bot/version.py (BFS up to max depth)."""
    if _has_required_files(tree):
        return tree
    queue: deque[tuple[Path, int]] = deque([(tree, 0)])
    while queue:
        node, depth = queue.popleft()
        if _has_required_files(node):
            return node
        if depth >= _MAX_RELEASE_ROOT_DEPTH:
            continue
        try:
            children = sorted(node.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name not in ("__MACOSX",):
                queue.append((child, depth + 1))
    if zip_path is not None:
        raise _missing_version_error(zip_path)
    raise UpdateError("فایل الزامی در ZIP نیست: bot/version.py")


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
    return _parse_version_from_text(version_py.read_text(encoding="utf-8"))


def _extract_release_zip(zip_path: Path, dest: Path) -> Path:
    """Extract release files, stripping any top-level folder prefix from ZIP paths."""
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        version_path = _find_bot_version_path_in_zip(zf, zip_path)
        prefix = _release_prefix_from_version_path(version_path)
        for info in zf.infolist():
            if info.is_dir():
                continue
            norm = _normalize_zip_path(info.filename)
            if ".." in norm.split("/"):
                raise UpdateError("فایل ZIP نامعتبر (مسیر ناامن).")
            if prefix:
                if not norm.startswith(prefix):
                    continue
                rel = norm[len(prefix) :]
            else:
                rel = norm
            if not rel:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
    return find_release_root(dest, zip_path=zip_path)


def inspect_release_zip(
    zip_path: Path,
    *,
    current_version: str = RUNNING_VERSION,
    allow_downgrade: bool = False,
) -> str:
    if not zip_path.is_file():
        raise UpdateError("فایل ZIP یافت نشد.")
    target = read_version_from_zip(zip_path)
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
    target = previous
    try:
        target = read_version_from_zip(zip_path)
        if compare_versions(target, previous) < 0 and not allow_downgrade:
            raise UpdateError("downgrade blocked")
        release_root = _extract_release_zip(zip_path, staging)
        create_backup(root)
        _copy_release_into_install(release_root, root)
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
