from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx

from xui.inbound_flow import resolve_flow_for_inbound_ids
from xui.link_fragment import (
    apply_fragment_to_vless_link,
    build_panel_link_fragment,
    decode_link_fragment,
)
from xui.models import ClientCreateRequest, XuiClientPayload

logger = logging.getLogger(__name__)

GB = 1024**3


@dataclass
class VlessConfig:
    link: str
    remark: str = ""


@dataclass
class ClientDelivery:
    vless_configs: list[VlessConfig] = field(default_factory=list)
    subscription_links: list[str] = field(default_factory=list)

    @property
    def vless_links(self) -> list[str]:
        return [c.link for c in self.vless_configs]


def gb_to_bytes(gb: float | int) -> int:
    return int(float(gb) * GB)


def bytes_to_gb(value: int) -> float:
    return round(value / GB, 2)


def read_limit_ip(client: dict[str, Any] | None) -> int:
    if not client:
        return 0
    raw = client.get("limitIp", client.get("limit_ip", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def read_comment(client: dict[str, Any] | None) -> str:
    if not client:
        return ""
    raw = client.get("comment")
    if raw is None:
        return ""
    return str(raw).strip()


def resolve_expiry_after_add_days(current_ms: int, days: int) -> int:
    """New expiry ms after adding days (extend from max(now, current) or from now)."""
    now_ms = int(time.time() * 1000)
    if current_ms > 0:
        base_ms = max(now_ms, current_ms)
    else:
        base_ms = now_ms
    return base_ms + int(days) * 86400 * 1000


def _build_client_update_payload(
    record: dict[str, Any], **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": record.get("email", ""),
        "enable": record.get("enable", True),
        "totalGB": record.get("totalGB", record.get("total_gb", 0)),
        "expiryTime": record.get("expiryTime", record.get("expiry_time", 0)),
        "limitIp": record.get("limitIp", record.get("limit_ip", 0)),
        "subId": record.get("subId") or record.get("sub_id") or "",
        "flow": record.get("flow") or "",
        "reset": record.get("reset", 0),
        "tgId": record.get("tgId", record.get("tg_id", 0)),
        "group": record.get("group") or "",
        "comment": record.get("comment") or "",
        "security": record.get("security") or "",
    }
    uuid_val = record.get("uuid")
    if isinstance(uuid_val, str) and uuid_val.strip():
        body["id"] = uuid_val.strip()
    else:
        raw_id = record.get("id")
        if isinstance(raw_id, str) and raw_id.strip() and "-" in raw_id:
            body["id"] = raw_id.strip()
    body.update(overrides)
    return body


def build_subscription_url(public_base: str, sub_id: str) -> str:
    base = public_base.rstrip("/")
    return f"{base}/{sub_id.strip()}"


class XuiError(Exception):
    pass


def _is_client_not_found(err: XuiError) -> bool:
    msg = str(err).lower()
    return "not found" in msg or "record not found" in msg


class XuiClient:
    """HTTP client for 3x-ui v3.2.0 panel API."""

    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
        max_retries: int = 3,
        sub_public_url: str | None = None,
        auto_vision_flow: bool = True,
        auto_reseller_group: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.sub_public_url = (sub_public_url or "").strip() or None
        self.auto_vision_flow = auto_vision_flow
        self.auto_reseller_group = auto_reseller_group
        self._csrf_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                verify=self.verify_ssl,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _csrf_headers(self) -> dict[str, str]:
        headers = self._auth_headers()
        if not self.api_token and self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        return headers

    async def ensure_authenticated(self) -> None:
        if self.api_token:
            return
        if not self.username or not self.password:
            raise XuiError("XUI_API_TOKEN or XUI_USERNAME/XUI_PASSWORD required")
        client = await self._get_client()
        r = await client.get("/csrf-token")
        r.raise_for_status()
        data = r.json()
        self._csrf_token = data.get("obj") or data.get("token")
        if not self._csrf_token:
            raise XuiError("Failed to obtain CSRF token")

        r = await client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
            },
            headers={
                **self._csrf_headers(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        body = r.json()
        if not body.get("success"):
            raise XuiError(body.get("msg", "Login failed"))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | list | None = None,
        params: dict | None = None,
    ) -> Any:
        await self.ensure_authenticated()
        client = await self._get_client()
        last_err: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                r = await client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=self._csrf_headers(),
                )
                if r.status_code == 401:
                    if not self.api_token:
                        self._csrf_token = None
                        await self.ensure_authenticated()
                    raise XuiError("Unauthorized — check panel credentials")
                if r.status_code == 403:
                    raise XuiError("Forbidden — check API token or CSRF")
                if not r.content:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise XuiError("Panel returned empty response")

                if r.headers.get("content-type", "").startswith("application/json"):
                    data = r.json()
                else:
                    data = {"success": r.is_success, "raw": r.text}

                if isinstance(data, dict) and data.get("success") is False:
                    raise XuiError(data.get("msg", "Panel API error"))
                return data
            except (httpx.HTTPError, XuiError) as e:
                last_err = e
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise
        raise last_err or XuiError("Request failed")

    async def resolve_client_flow(self, inbound_ids: list[int]) -> str:
        if not self.auto_vision_flow or not inbound_ids:
            return ""
        inbounds = await self.list_inbounds()
        flow = resolve_flow_for_inbound_ids(inbounds, inbound_ids)
        logger.debug(
            "Resolved client flow for inbound_ids=%s: %r",
            inbound_ids,
            flow or "(empty)",
        )
        return flow

    async def ensure_client_group(self, name: str) -> None:
        group = name.strip()
        if not group:
            return
        try:
            await self._request(
                "POST",
                "/panel/api/clients/groups/create",
                json={"name": group},
            )
        except XuiError as e:
            msg = str(e).lower()
            if "already exists" in msg or "exist" in msg:
                return
            raise

    async def assign_client_to_group(self, email: str, group: str) -> None:
        group_name = group.strip()
        if not group_name:
            return
        await self.ensure_client_group(group_name)
        await self._request(
            "POST",
            "/panel/api/clients/groups/bulkAdd",
            json={"emails": [email], "group": group_name},
        )
        logger.debug("Assigned client %s to panel group %r", email, group_name)

    async def create_client(
        self,
        email: str,
        volume_gb: float,
        inbound_ids: list[int],
        *,
        expiry_days: int = 0,
        limit_ip: int = 0,
        flow: str = "",
        group: str = "",
    ) -> tuple[dict[str, Any], str]:
        if flow == "":
            flow = await self.resolve_client_flow(inbound_ids)

        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int((time.time() + expiry_days * 86400) * 1000)

        sub_id = uuid.uuid4().hex[:16]
        group_name = group.strip()
        if group_name:
            await self.ensure_client_group(group_name)
        payload = ClientCreateRequest(
            client=XuiClientPayload(
                email=email,
                totalGB=gb_to_bytes(volume_gb),
                expiryTime=expiry_ms,
                enable=True,
                limitIp=limit_ip,
                subId=sub_id,
                flow=flow,
                group=group_name,
            ),
            inboundIds=inbound_ids,
        )
        result = await self._request(
            "POST",
            "/panel/api/clients/add",
            json=payload.model_dump(),
        )
        if group.strip():
            try:
                await self.assign_client_to_group(email, group)
            except XuiError as e:
                logger.warning(
                    "Client %s created but group assignment failed: %s",
                    email,
                    e,
                )
        return result, sub_id

    async def delete_client(self, email: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"/panel/api/clients/del/{quote(email, safe='')}"
        )

    async def get_traffic(self, email: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/panel/api/clients/traffic/{quote(email, safe='')}"
        )
        return data.get("obj", data) if isinstance(data, dict) else data

    async def get_client(self, email: str) -> dict[str, Any] | None:
        try:
            data = await self._request(
                "GET", f"/panel/api/clients/get/{quote(email, safe='')}"
            )
        except XuiError as e:
            if _is_client_not_found(e):
                return None
            raise
        obj = data.get("obj", data) if isinstance(data, dict) else data
        if isinstance(obj, dict):
            client = obj.get("client")
            if isinstance(client, dict):
                return client
        return None

    async def _get_client_dict_for_update(self, email: str) -> dict[str, Any]:
        client = await self.get_client(email)
        if not client:
            raise XuiError("کلاینت یافت نشد.")
        return client

    async def set_client_enabled(self, email: str, enabled: bool) -> dict[str, Any]:
        client = await self._get_client_dict_for_update(email)
        payload = _build_client_update_payload(client, enable=enabled)
        return await self._request(
            "POST",
            f"/panel/api/clients/update/{quote(email, safe='')}",
            json=payload,
        )

    async def reset_client_traffic(self, email: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/panel/api/clients/resetTraffic/{quote(email, safe='')}",
        )

    async def update_client_fields(
        self,
        email: str,
        *,
        limit_ip: int | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        if limit_ip is None and comment is None:
            raise XuiError("هیچ فیلدی برای به‌روزرسانی مشخص نشده.")
        client = await self._get_client_dict_for_update(email)
        overrides: dict[str, Any] = {}
        if limit_ip is not None:
            overrides["limitIp"] = limit_ip
        if comment is not None:
            overrides["comment"] = comment
        payload = _build_client_update_payload(client, **overrides)
        return await self._request(
            "POST",
            f"/panel/api/clients/update/{quote(email, safe='')}",
            json=payload,
        )

    async def add_client_expiry_days(self, email: str, days: int) -> dict[str, Any]:
        if days < 1:
            raise XuiError("تعداد روز باید حداقل ۱ باشد.")
        return await self._request(
            "POST",
            "/panel/api/clients/bulkAdjust",
            json={"emails": [email], "addDays": days, "addBytes": 0},
        )

    async def add_client_traffic_bytes(
        self, email: str, add_bytes: int
    ) -> dict[str, Any]:
        if add_bytes < 1:
            raise XuiError("حجم اضافه باید بزرگ‌تر از صفر باشد.")
        return await self._request(
            "POST",
            "/panel/api/clients/bulkAdjust",
            json={"emails": [email], "addDays": 0, "addBytes": add_bytes},
        )

    async def set_client_expiry_ms(self, email: str, expiry_ms: int) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/panel/api/clients/get/{quote(email, safe='')}"
        )
        obj = data.get("obj", data) if isinstance(data, dict) else data
        if not isinstance(obj, dict):
            raise XuiError("کلاینت یافت نشد.")
        client = obj.get("client")
        if not isinstance(client, dict):
            raise XuiError("کلاینت یافت نشد.")
        payload = _build_client_update_payload(client, expiryTime=expiry_ms)
        return await self._request(
            "POST",
            f"/panel/api/clients/update/{quote(email, safe='')}",
            json=payload,
        )

    @staticmethod
    def extract_sub_id(client: dict[str, Any] | None) -> str | None:
        if not client:
            return None
        sub_id = client.get("subId") or client.get("sub_id")
        if sub_id is None:
            return None
        text = str(sub_id).strip()
        return text or None

    async def get_links(self, email: str) -> list[VlessConfig]:
        data = await self._request(
            "GET", f"/panel/api/clients/links/{quote(email, safe='')}"
        )
        obj = data.get("obj", data) if isinstance(data, dict) else data
        return _normalize_vless_configs(obj)

    async def get_sub_links(self, sub_id: str) -> list[str]:
        if not sub_id.strip():
            return []
        data = await self._request(
            "GET",
            f"/panel/api/clients/subLinks/{quote(sub_id, safe='')}",
        )
        obj = data.get("obj", data) if isinstance(data, dict) else data
        return _normalize_links(obj, subscription_urls=True)

    async def get_client_delivery(
        self,
        email: str,
        sub_id: str | None = None,
        *,
        total_bytes: int | None = None,
    ) -> ClientDelivery:
        vless_configs = await self.get_links(email)
        if total_bytes is not None and total_bytes > 0:
            fragment = build_panel_link_fragment(email, total_bytes)
            patched: list[VlessConfig] = []
            for cfg in vless_configs:
                new_link = apply_fragment_to_vless_link(cfg.link, fragment)
                patched.append(
                    VlessConfig(
                        link=new_link,
                        remark=cfg.remark or decode_link_fragment(new_link),
                    )
                )
            vless_configs = patched
        try:
            inbounds = await self.list_inbounds()
            vless_configs = enrich_vless_remarks_from_inbounds(vless_configs, inbounds)
        except XuiError as e:
            logger.warning("list_inbounds for remark enrichment failed: %s", e)

        resolved_sub_id = (sub_id or "").strip() or None
        if not resolved_sub_id:
            client = await self.get_client(email)
            resolved_sub_id = self.extract_sub_id(client)

        subscription_links: list[str] = []
        if resolved_sub_id:
            if self.sub_public_url:
                subscription_links.append(
                    build_subscription_url(self.sub_public_url, resolved_sub_id)
                )
            try:
                api_links = await self.get_sub_links(resolved_sub_id)
                for link in api_links:
                    if link not in subscription_links:
                        subscription_links.append(link)
            except XuiError as e:
                logger.warning("get_sub_links failed for %s: %s", resolved_sub_id, e)

        return ClientDelivery(
            vless_configs=vless_configs,
            subscription_links=subscription_links,
        )

    async def list_inbounds(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/panel/api/inbounds/list")
        obj = data.get("obj", data) if isinstance(data, dict) else data
        if isinstance(obj, list):
            return obj
        return []


def _inbound_remark(inbound: dict[str, Any]) -> str:
    return str(
        inbound.get("remark") or inbound.get("tag") or inbound.get("name") or ""
    ).strip()


def _inbound_port(inbound: dict[str, Any]) -> int | None:
    raw = inbound.get("port")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_vless_link_meta(link: str) -> tuple[int | None, str]:
    parsed = urlparse(link)
    port = parsed.port
    fragment = unquote(parsed.fragment).strip() if parsed.fragment else ""
    return port, fragment


def enrich_vless_remarks_from_inbounds(
    configs: list[VlessConfig],
    inbounds: list[dict[str, Any]],
) -> list[VlessConfig]:
    """3x-ui /clients/links returns plain strings; remarks live on inbound rows."""
    by_port: dict[int, str] = {}
    for ib in inbounds:
        port = _inbound_port(ib)
        remark = _inbound_remark(ib)
        if port is not None and remark:
            by_port[port] = remark

    enriched: list[VlessConfig] = []
    for cfg in configs:
        remark = cfg.remark
        port, fragment = _parse_vless_link_meta(cfg.link)
        if not remark and fragment:
            remark = fragment
        if not remark and port is not None and port in by_port:
            remark = by_port[port]
        if not remark and port is not None:
            remark = f"پورت {port}"
        enriched.append(VlessConfig(link=cfg.link, remark=remark))
    return enriched


def _normalize_vless_configs(obj: Any) -> list[VlessConfig]:
    if obj is None:
        return []
    if isinstance(obj, str):
        text = obj.strip()
        if text and text.startswith(("vless://", "vmess://", "trojan://", "ss://")):
            return [VlessConfig(link=text)]
        return []
    if isinstance(obj, list):
        out: list[VlessConfig] = []
        for item in obj:
            out.extend(_normalize_vless_configs(item))
        return _dedupe_vless(out)
    if isinstance(obj, dict):
        direct = _vless_config_from_dict(obj)
        if direct:
            return [direct]
        out: list[VlessConfig] = []
        for key in ("links", "obj", "data"):
            if key in obj:
                out.extend(_normalize_vless_configs(obj[key]))
        return _dedupe_vless(out)
    return []


def _vless_config_from_dict(d: dict[str, Any]) -> VlessConfig | None:
    link = ""
    for key in ("link", "url", "vless"):
        val = d.get(key)
        if isinstance(val, str) and val.strip().startswith(
            ("vless://", "vmess://", "trojan://", "ss://")
        ):
            link = val.strip()
            break
    if not link:
        return None
    remark = str(d.get("remark") or d.get("tag") or d.get("name") or "").strip()
    return VlessConfig(link=link, remark=remark)


def _dedupe_vless(items: list[VlessConfig]) -> list[VlessConfig]:
    seen: set[str] = set()
    out: list[VlessConfig] = []
    for item in items:
        if item.link not in seen:
            seen.add(item.link)
            out.append(item)
    return out


def _normalize_links(
    obj: Any,
    *,
    vless_only: bool = False,
    subscription_urls: bool = False,
) -> list[str]:
    if obj is None:
        return []
    if isinstance(obj, str):
        return [obj] if obj.strip() else []
    if isinstance(obj, list):
        out: list[str] = []
        for item in obj:
            if isinstance(item, str) and item.strip():
                if _link_matches_filter(item, vless_only, subscription_urls):
                    out.append(item)
            elif isinstance(item, dict):
                out.extend(
                    _links_from_dict(item, vless_only=vless_only, subscription_urls=subscription_urls)
                )
        return _dedupe(out)
    if isinstance(obj, dict):
        return _dedupe(
            _links_from_dict(obj, vless_only=vless_only, subscription_urls=subscription_urls)
        )
    return []


def _links_from_dict(
    d: dict[str, Any],
    *,
    vless_only: bool,
    subscription_urls: bool,
) -> list[str]:
    out: list[str] = []
    sub_keys = ("subUrl", "subJsonUrl", "subClashUrl", "subscription", "sub")
    vless_keys = ("link", "url", "vless")

    if subscription_urls:
        for key in sub_keys:
            val = d.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
        for key in ("links", "obj", "data"):
            if key in d:
                out.extend(_normalize_links(d[key], subscription_urls=True))

    if vless_only or not subscription_urls:
        for key in vless_keys:
            val = d.get(key)
            if isinstance(val, str) and val.strip():
                text = val.strip()
                if text.startswith("vless://") or text.startswith("vmess://") or not subscription_urls:
                    if _link_matches_filter(text, vless_only, subscription_urls):
                        out.append(text)
        for key in ("links", "obj", "data"):
            if key in d and not subscription_urls:
                out.extend(_normalize_links(d[key], vless_only=vless_only))

    if not vless_only and not subscription_urls:
        for val in d.values():
            if isinstance(val, str) and val.strip().startswith(("http://", "https://", "vless://")):
                out.append(val.strip())

    return out


def _link_matches_filter(
    link: str, vless_only: bool, subscription_urls: bool
) -> bool:
    if vless_only:
        return link.startswith(("vless://", "vmess://", "trojan://", "ss://"))
    if subscription_urls:
        return link.startswith(("http://", "https://")) or "/sub/" in link
    return True


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
