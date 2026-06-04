import json
import zipfile
from pathlib import Path

import pytest

from bot.version import __version__
from services.updater import (
    UpdateError,
    compare_versions,
    find_release_root,
    inspect_release_zip,
    parse_version,
    read_version_from_tree,
    read_version_from_zip,
)


def test_parse_version() -> None:
    assert parse_version("1.0.0") == (1, 0, 0)
    assert compare_versions("1.0.0", "1.1.0") < 0
    assert compare_versions("2.0.0", "1.9.9") > 0


def test_read_version_from_release_json(tmp_path: Path) -> None:
    (tmp_path / "RELEASE.json").write_text(
        json.dumps({"version": "1.2.3"}), encoding="utf-8"
    )
    (tmp_path / "bot").mkdir()
    (tmp_path / "bot" / "version.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8"
    )
    assert read_version_from_tree(tmp_path) == "1.2.3"


def test_inspect_release_zip(tmp_path: Path) -> None:
    tree = tmp_path / "pkg"
    (tree / "bot").mkdir(parents=True)
    (tree / "bot" / "version.py").write_text(
        '__version__ = "1.1.0"\n', encoding="utf-8"
    )
    (tree / "RELEASE.json").write_text(
        json.dumps({"version": "1.1.0"}), encoding="utf-8"
    )
    zip_path = tmp_path / "rel.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in tree.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(tree).as_posix())
    assert inspect_release_zip(zip_path, current_version="1.0.0") == "1.1.0"


def test_inspect_rejects_downgrade(tmp_path: Path) -> None:
    tree = tmp_path / "pkg"
    (tree / "bot").mkdir(parents=True)
    (tree / "bot" / "version.py").write_text(
        '__version__ = "0.9.0"\n', encoding="utf-8"
    )
    zip_path = tmp_path / "old.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("bot/version.py", '__version__ = "0.9.0"\n')
    with pytest.raises(UpdateError):
        inspect_release_zip(zip_path, current_version=__version__)


def test_inspect_rejects_same_version(tmp_path: Path) -> None:
    zip_path = tmp_path / "same.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("bot/version.py", f'__version__ = "{__version__}"\n')
    with pytest.raises(UpdateError):
        inspect_release_zip(zip_path, current_version=__version__)


def test_find_release_root_nested(tmp_path: Path) -> None:
    inner = tmp_path / "resellerbot-1.1.0"
    (inner / "bot").mkdir(parents=True)
    (inner / "bot" / "version.py").write_text(
        '__version__ = "1.1.0"\n', encoding="utf-8"
    )
    root = find_release_root(tmp_path)
    assert root == inner


def test_find_release_root_double_nested(tmp_path: Path) -> None:
    inner = tmp_path / "outer" / "inner"
    (inner / "bot").mkdir(parents=True)
    (inner / "bot" / "version.py").write_text(
        '__version__ = "1.1.0"\n', encoding="utf-8"
    )
    root = find_release_root(tmp_path)
    assert root == inner


def test_find_release_root_triple_nested(tmp_path: Path) -> None:
    inner = tmp_path / "a" / "b" / "c"
    (inner / "bot").mkdir(parents=True)
    (inner / "bot" / "version.py").write_text(
        '__version__ = "1.1.0"\n', encoding="utf-8"
    )
    root = find_release_root(tmp_path)
    assert root == inner


def test_inspect_nested_github_style_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "github.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "resellerbot-1.1.0/bot/version.py", '__version__ = "1.1.0"\n'
        )
        zf.writestr(
            "resellerbot-1.1.0/RELEASE.json",
            json.dumps({"version": "1.1.0"}),
        )
    assert inspect_release_zip(zip_path, current_version="1.0.0") == "1.1.0"


def test_read_version_from_zip_flat(tmp_path: Path) -> None:
    zip_path = tmp_path / "flat.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("bot/version.py", '__version__ = "1.2.0"\n')
        zf.writestr("RELEASE.json", json.dumps({"version": "1.2.0"}))
    assert read_version_from_zip(zip_path) == "1.2.0"


def test_read_version_from_zip_github_prefix(tmp_path: Path) -> None:
    zip_path = tmp_path / "prefixed.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "resellerbot-1.2.0/bot/version.py", '__version__ = "1.2.0"\n'
        )
        zf.writestr(
            "resellerbot-1.2.0/RELEASE.json",
            json.dumps({"version": "1.2.0"}),
        )
    assert read_version_from_zip(zip_path) == "1.2.0"


def test_missing_version_shows_zip_sample(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("version.py", '__version__ = "1.1.0"\n')
    with pytest.raises(UpdateError, match="bot/version.py") as exc:
        inspect_release_zip(zip_path, current_version="1.0.0")
    assert "نمونه مسیرهای داخل ZIP" in str(exc.value)


def test_read_version_from_zip_without_extract(tmp_path: Path) -> None:
    """inspect reads version from namelist only — no staging dir needed."""
    zip_path = tmp_path / "noextract.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("pkg/bot/version.py", '__version__ = "2.0.0"\n')
        zf.writestr("pkg/RELEASE.json", json.dumps({"version": "2.0.0"}))
    staging = tmp_path / "should_not_exist"
    assert not staging.exists()
    assert inspect_release_zip(zip_path, current_version="1.0.0") == "2.0.0"
    assert not staging.exists()
