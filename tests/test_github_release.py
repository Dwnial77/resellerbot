"""Tests for GitHub release auto-update."""

import asyncio
import json
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.github_release import GitHubReleaseError, fetch_latest_release_zip


def _release_json(*, assets: list[dict]) -> dict:
    return {
        "tag_name": "v1.2.0",
        "assets": assets,
    }


def _make_zip_bytes(version: str = "1.2.0") -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bot/version.py", f'__version__ = "{version}"\n')
        zf.writestr("RELEASE.json", json.dumps({"version": version}))
    return buf.getvalue()


def _mock_response(*, status: int = 200, json_data=None, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.content = content
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
        if status >= 400
        else None
    )
    return resp


def test_fetch_latest_release_zip_success() -> None:
    async def _run() -> None:
        zip_bytes = _make_zip_bytes("1.2.0")
        release = _release_json(
            assets=[
                {
                    "name": "resellerbot-1.2.0-source.zip",
                    "browser_download_url": "https://example.com/source.zip",
                    "size": 100,
                },
                {
                    "name": "resellerbot-1.2.0.zip",
                    "browser_download_url": "https://example.com/release.zip",
                    "size": len(zip_bytes),
                },
            ]
        )

        async def fake_get(url: str, **kwargs):
            if url.endswith("/releases/latest"):
                return _mock_response(json_data=release)
            if url == "https://example.com/release.zip":
                return _mock_response(content=zip_bytes)
            return _mock_response(status=404)

        client = AsyncMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "services.github_release.httpx.AsyncClient", return_value=client
        ):
            version, raw, filename = await fetch_latest_release_zip(
                "owner/repo", max_bytes=1_000_000
            )
        assert version == "1.2.0"
        assert filename == "resellerbot-1.2.0.zip"
        assert raw == zip_bytes

    asyncio.run(_run())


def test_fetch_rejects_only_source_zip() -> None:
    async def _run() -> None:
        release = _release_json(
            assets=[
                {
                    "name": "resellerbot-1.2.0-source.zip",
                    "browser_download_url": "https://example.com/source.zip",
                    "size": 100,
                },
            ]
        )
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_mock_response(json_data=release)
        )
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "services.github_release.httpx.AsyncClient", return_value=client
        ):
            with pytest.raises(GitHubReleaseError, match="ZIP"):
                await fetch_latest_release_zip("owner/repo", max_bytes=1_000_000)

    asyncio.run(_run())


def test_fetch_rejects_oversized_asset() -> None:
    async def _run() -> None:
        release = _release_json(
            assets=[
                {
                    "name": "resellerbot-1.2.0.zip",
                    "browser_download_url": "https://example.com/release.zip",
                    "size": 10_000_000,
                },
            ]
        )
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_mock_response(json_data=release)
        )
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "services.github_release.httpx.AsyncClient", return_value=client
        ):
            with pytest.raises(GitHubReleaseError, match="حد"):
                await fetch_latest_release_zip("owner/repo", max_bytes=1000)

    asyncio.run(_run())


def test_fetch_network_error() -> None:
    async def _run() -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "services.github_release.httpx.AsyncClient", return_value=client
        ):
            with pytest.raises(GitHubReleaseError, match="GitHub"):
                await fetch_latest_release_zip("owner/repo", max_bytes=1_000_000)

    asyncio.run(_run())
