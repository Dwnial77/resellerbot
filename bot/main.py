import asyncio
import logging
import sys
from pathlib import Path

# Allow running as `python -m bot.main` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.commands import setup_bot_commands
from bot.config import get_settings
from bot.handlers import setup_routers
from bot.middlewares.auth import RateLimitMiddleware
from bot.middlewares.deps import PanelMiddleware
from bot.tasks.usage_monitor import usage_alert_loop
from bot.texts import fa as t
from bot.version import __version__
from db.session import get_session_factory, init_db
from services.panel_registry import PanelRegistry
from services.updater import apply_pending_update, load_update_result, project_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def _notify_update_result(bot: Bot, admin_ids: list[int]) -> None:
    result = load_update_result(project_root())
    if result is None:
        return
    if result.success:
        text = t.BOT_UPDATE_RESULT_OK.format(
            previous=result.previous_version,
            new_version=result.new_version,
            message=result.message,
        )
    else:
        text = t.BOT_UPDATE_RESULT_FAIL.format(
            previous=result.previous_version,
            message=result.message,
        )
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.warning("Could not notify admin %s of update: %s", admin_id, e)


async def main() -> None:
    root = project_root()
    settings = get_settings()
    logger.info("Reseller bot %s starting (root=%s)", __version__, root)

    applied = apply_pending_update(
        root, allow_downgrade=settings.allow_update_downgrade
    )
    if applied is not None:
        if applied.success:
            logger.info("Update applied: %s", applied.message)
        else:
            logger.error("Update failed: %s", applied.message)

    await init_db()

    registry = PanelRegistry()
    async with get_session_factory()() as session:
        await registry.load_from_db(session)

    for panel_id in registry.loaded_panel_ids():
        client = registry.get_client(panel_id)
        try:
            await client.ensure_authenticated()
            logger.info("Connected to 3x-ui panel #%s", panel_id)
        except Exception as e:
            logger.warning(
                "Panel #%s auth check failed (will retry on requests): %s",
                panel_id,
                e,
            )

    bot = Bot(token=settings.bot_token)
    await _notify_update_result(bot, settings.admin_telegram_ids)
    await setup_bot_commands(bot, settings.admin_telegram_ids)

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(PanelMiddleware(registry))
    dp.update.middleware(RateLimitMiddleware())
    dp.include_router(setup_routers())

    monitor_task = asyncio.create_task(
        usage_alert_loop(bot, registry), name="usage_alert_monitor"
    )
    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        await registry.close_all()


if __name__ == "__main__":
    asyncio.run(main())
