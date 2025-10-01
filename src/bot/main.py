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
from bot.middlewares.whitelist import WhitelistMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.handlers import commands as commands_handlers
from bot.handlers import flow_add_operation as flow_handlers
from bot.db.base import init_engine, ensure_schema, session_scope
from bot.types.enums import DEFAULT_CATEGORY_SEED
from bot.db.models import Category, Channel
from bot.services.time import now_msk

logger = logging.getLogger(__name__)


async def on_startup(dp: Dispatcher, settings: Settings) -> None:
    ensure_schema("finance")
    run_migrations(settings)
    seed_categories()
    seed_channels()
    logger.info("Bot is ready")


def run_migrations(settings: Settings) -> None:
    from alembic.config import Config
    from alembic import command

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("script_location", os.path.join(project_root, "src/bot/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
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


def seed_channels() -> None:
    # Provided list of channels to show in selection UI
    provided_titles = [
        "Футбол OnSide",
        "OnSide: новости футбола",
        "Футбол OnSide GPT",
        "PSG: фан-клуб ПСЖ",
        "Футбол Испании: La Liga",
        "Футбол России: РПЛ, Кубок",
    ]
    # Deterministic synthetic tg_chat_id values for seed (unique, positive)
    synthetic_ids = [1000000001, 1000000002, 1000000003, 1000000004, 1000000005, 1000000006]

    with session_scope() as s:
        # Map existing by title to avoid duplicates if partially present
        existing_by_title: dict[str, int] = {
            (ch.title or ""): ch.id for ch in s.query(Channel).all()
        }
        for idx, title in enumerate(provided_titles):
            if title in existing_by_title:
                continue
            ch = Channel(
                tg_chat_id=synthetic_ids[idx],
                title=title,
                username=None,
                created_at=now_msk(),
            )
            s.add(ch)
        s.flush()


async def main() -> None:
    settings = Settings.load()
    setup_logging(settings.log_level)
    logger.info("Starting bot with tz=%s", settings.tz)

    init_engine(settings.database_url)

    storage = MemoryStorage()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)

    dp.message.middleware(WhitelistMiddleware(settings))
    dp.callback_query.middleware(WhitelistMiddleware(settings))
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    dp.include_router(commands_handlers.router)
    dp.include_router(flow_handlers.router)

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
        await on_startup(dp, settings)
        polling = asyncio.create_task(
            dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        )
        # wait for either stop signal or polling finishes
        done, pending = await asyncio.wait(
            {polling, asyncio.create_task(stop_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_event.is_set():
            with suppress(Exception):
                dp.stop_polling()
        if not polling.done():
            polling.cancel()
            with suppress(asyncio.CancelledError):
                await polling
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
    finally:
        with suppress(Exception):
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
