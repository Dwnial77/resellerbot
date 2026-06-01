"""Background task: notify resellers at 80% / 90% quota or client traffic usage."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from bot.config import get_settings
from db.session import get_session_factory
from services.panel_registry import PanelRegistry
from services.usage_alerts import run_usage_alert_cycle

logger = logging.getLogger(__name__)


async def usage_alert_loop(bot: Bot, registry: PanelRegistry) -> None:
    settings = get_settings()
    if not settings.usage_alert_enabled:
        logger.info("Usage alerts disabled (USAGE_ALERT_ENABLED=false)")
        return
    interval = max(60, settings.usage_alert_interval_seconds)
    logger.info("Usage alert monitor started (interval=%ss)", interval)
    while True:
        try:
            async with get_session_factory()() as session:
                count = await run_usage_alert_cycle(bot, registry, session)
            if count:
                logger.info("Usage alerts sent: %d", count)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Usage alert cycle failed: %s", e)
        await asyncio.sleep(interval)
