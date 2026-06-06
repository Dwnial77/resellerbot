"""Fetch latest release ZIP from GitHub Releases API."""

from __future__ import annotations

import re
from typing import Any

import httpx

_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)$")
_GITHUB_API = "https://api.github.com"
_USER_AGENT = "resellerbot-updater"


class GitHubReleaseError(Exception):
    pass


def _parse_version_from_asset(name: str, prefix: str) -> str | None:
    if not name.startswith(prefix) or not name.endswith(".zip"):
        return None
    if name.endswith("-source.zip"):
        return None
    stem = name[: -len(".zip")]
    if not stem.startswith(prefix):
        return None
    version = stem[len(prefix) :]
    if _VERSION_RE.match(version):
        return version
    return None


def _pick_release_asset(
    assets: list[dict[str, Any]], *, asset_prefix: str
) -> dict[str, Any]:
    for asset in assets:
        name = asset.get("name")
        if not isinstance(name, str):
            continue
        if _parse_version_from_asset(name, asset_prefix) is None:
            continue
        url = asset.get("browser_download_url")
        if isinstance(url, str) and url.strip():
            return asset
    raise GitHubReleaseError(
        f"فایل ZIP ریلیز ({asset_prefix}*.zip) در آخرین release یافت نشد."
    )


def _version_from_tag(tag: str) -> str | None:
    tag = tag.strip()
    if tag.startswith("v"):
        tag = tag[1:]
    if _VERSION_RE.match(tag):
        return tag
    return None


async def fetch_latest_release_zip(
    repo: str,
    *,
    max_bytes: int,
    asset_prefix: str = "resellerbot-",
) -> tuple[str, bytes, str]:
    """Return (version, zip_bytes, filename) for the latest GitHub release asset."""
    repo = repo.strip().strip("/")
    if "/" not in repo:
        raise GitHubReleaseError("GITHUB_REPO نامعتبر است (فرمت: owner/repo).")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
    }
    api_url = f"{_GITHUB_API}/repos/{repo}/releases/latest"

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            release_resp = await client.get(api_url, headers=headers)
            if release_resp.status_code == 404:
                raise GitHubReleaseError("release فعالی در GitHub یافت نشد.")
            release_resp.raise_for_status()
            release = release_resp.json()
            if not isinstance(release, dict):
                raise GitHubReleaseError("پاسخ GitHub نامعتبر است.")

            assets = release.get("assets")
            if not isinstance(assets, list):
                assets = []
            asset = _pick_release_asset(assets, asset_prefix=asset_prefix)
            filename = str(asset["name"])
            version = _parse_version_from_asset(filename, asset_prefix)
            if not version:
                tag = release.get("tag_name")
                if isinstance(tag, str):
                    version = _version_from_tag(tag)
            if not version:
                raise GitHubReleaseError("نسخه release از GitHub استخراج نشد.")

            size = asset.get("size")
            if isinstance(size, int) and size > max_bytes:
                raise GitHubReleaseError("حجم فایل release بیش از حد مجاز است.")

            download_url = str(asset["browser_download_url"])
            zip_resp = await client.get(download_url, headers=headers)
            zip_resp.raise_for_status()
            raw = zip_resp.content
    except GitHubReleaseError:
        raise
    except httpx.HTTPStatusError as e:
        raise GitHubReleaseError(
            f"خطای GitHub API: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise GitHubReleaseError(
            f"اتصال به GitHub برقرار نشد: {e}"
        ) from e

    if len(raw) > max_bytes:
        raise GitHubReleaseError("حجم فایل دانلود شده بیش از حد مجاز است.")
    if len(raw) < 1:
        raise GitHubReleaseError("فایل ZIP خالی است.")

    return version, raw, filename
