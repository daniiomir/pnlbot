from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import suppress

# Load .env if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.settings import Settings, setup_logging
from bot.services.mtproto_client import init_telethon, shutdown_telethon
from bot.services.scheduler import add_daily_job, shutdown_scheduler
from bot.middlewares import (
    ErrorLoggingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    WhitelistMiddleware,
)
from bot.handlers import commands as commands_handlers
from bot.handlers import flow_add_operation as flow_handlers
from bot.handlers import channels as channels_handlers
from bot.db.base import init_engine, ensure_schema, session_scope
from bot.types.enums import DEFAULT_CATEGORY_SEED
from bot.db.models import Category, Channel
from bot.services.time import now_msk

logger = logging.getLogger(__name__)


async def on_startup(dp: Dispatcher, settings: Settings) -> None:
    ensure_schema("finance")
    run_migrations(settings)
    seed_categories()
    deactivate_legacy_seeded_channels()
    # Initialize Telethon client
    await init_telethon(settings)
    logger.info("Bot is ready")


def run_migrations(settings: Settings) -> None:
    from alembic.config import Config
    from alembic import command

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("script_location", os.path.join(project_root, "src/bot/db/migrations"))
    # Escape '%' for configparser interpolation in alembic Config
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    os.environ.setdefault("DATABASE_URL", settings.database_url)
    logger.info("Running migrations via Alembic API")
    command.upgrade(cfg, "head")


def seed_categories() -> None:
    with session_scope() as s:
        exists = s.query(Category).count()
        if exists:
            return
        for code, name in DEFAULT_CATEGORY_SEED:
            s.add(Category(code=code, name=name, is_active=True))
        s.flush()


def deactivate_legacy_seeded_channels() -> None:
    # Deactivate any channels that were not added via new binding flow
    # Heuristic: channels with added_by_user_id IS NULL are considered legacy
    with session_scope() as s:
        rows = (
            s.query(Channel)
            .filter(Channel.added_by_user_id.is_(None), Channel.is_active.is_(True))
            .all()
        )
        changed = 0
        for ch in rows:
            ch.is_active = False
            changed += 1
        if changed:
            logger.info("Deactivated %s legacy channels (no added_by_user_id)", changed)


async def main() -> None:
    settings = Settings.load()
    setup_logging(settings.log_level)
    logger.info("Starting bot with tz=%s", settings.tz)

    init_engine(settings.database_url)

    storage = MemoryStorage()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)

    # Middlewares order: error logging -> logging -> rate limit -> whitelist
    # Update-level middlewares to ensure we log every incoming update
    dp.update.middleware(ErrorLoggingMiddleware())
    dp.update.middleware(LoggingMiddleware())

    # Fallback errors handler at dispatcher level (logs any unhandled exceptions)
    async def _errors_handler(event, exception):  # type: ignore[no-redef]
        logging.getLogger(__name__).exception("Unhandled error: %s", exception)
        logging.getLogger().exception("Unhandled error (root): %s", exception)
        return True


    dp.errors.register(_errors_handler)  # type: ignore[attr-defined]


    dp.message.middleware(ErrorLoggingMiddleware())
    dp.callback_query.middleware(ErrorLoggingMiddleware())
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(WhitelistMiddleware(settings))
    dp.callback_query.middleware(WhitelistMiddleware(settings))

    dp.include_router(commands_handlers)
    dp.include_router(flow_handlers)
    dp.include_router(channels_handlers)

    # Graceful shutdown on Ctrl+C / SIGTERM
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        stop_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, _signal_handler)
    except Exception:
        pass

    try:
        # Ensure no webhook blocks polling
        with suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=False)
        await on_startup(dp, settings)
        # Re-apply logging configuration after migrations in case Alembic altered handlers
        setup_logging(settings.log_level)
        # Schedule daily job
        add_daily_job(bot)
        # Run polling synchronously so stdout/file logging flushes in-order
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
    finally:
        with suppress(Exception):
            await bot.session.close()
        # Shutdown Telethon
        with suppress(Exception):
            await shutdown_telethon()
        # Shutdown scheduler
        with suppress(Exception):
            shutdown_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
