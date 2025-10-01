from __future__ import annotations

import asyncio
import logging
import os
import subprocess

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.settings import Settings, setup_logging
from bot.middlewares.whitelist import WhitelistMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.handlers import commands as commands_handlers
from bot.handlers import flow_add_operation as flow_handlers
from bot.db.base import init_engine, ensure_schema, session_scope
from bot.types.enums import DEFAULT_CATEGORY_SEED
from bot.db.models import Category

logger = logging.getLogger(__name__)


async def on_startup(dp: Dispatcher, settings: Settings) -> None:
    ensure_schema("finance")
    run_migrations()
    seed_categories()
    logger.info("Bot is ready")


def run_migrations() -> None:
    cmd = ["alembic", "upgrade", "head"]
    logger.info("Running migrations: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def seed_categories() -> None:
    with session_scope() as s:
        exists = s.query(Category).count()
        if exists:
            return
        for code, name in DEFAULT_CATEGORY_SEED:
            s.add(Category(code=code, name=name, is_active=True))
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

    await on_startup(dp, settings)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
