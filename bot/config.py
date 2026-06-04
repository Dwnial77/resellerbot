from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.utils.panel_url import normalize_http_url, normalize_sub_public_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    admin_telegram_ids: list[int] = []

    xui_base_url: str
    xui_api_token: str | None = None
    xui_username: str | None = None
    xui_password: str | None = None
    xui_verify_ssl: bool = True
    xui_default_inbound_ids: list[int] = [1]
    xui_sub_public_url: str | None = None
    xui_auto_vision_flow: bool = True
    xui_auto_reseller_group: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    create_rate_limit: int = 5
    quota_refund_max_traffic_gb: float = 1.0

    usage_alert_enabled: bool = True
    usage_alert_interval_seconds: int = 300

    update_zip_max_bytes: int = 52_428_800
    systemd_service_name: str = "resellerbot"
    allow_update_downgrade: bool = False

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return v

    @field_validator("xui_default_inbound_ids", mode="before")
    @classmethod
    def parse_inbound_ids(cls, v):
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            if not v.strip():
                return [1]
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return [1]

    @field_validator("xui_base_url", mode="before")
    @classmethod
    def normalize_xui_base_url(cls, v: str) -> str:
        return normalize_http_url(str(v).strip())

    @field_validator("xui_sub_public_url", mode="before")
    @classmethod
    def normalize_xui_sub_public_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        raw = str(v).strip()
        if not raw:
            return None
        return normalize_sub_public_url(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()
