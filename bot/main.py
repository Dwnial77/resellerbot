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

from db.session import get_session_factory, init_db

from services.panel_registry import PanelRegistry



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",

)

logger = logging.getLogger(__name__)





async def main() -> None:

    settings = get_settings()

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


