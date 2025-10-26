from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from bot.services.time import MSK_TZ
from bot.services.channel_stats import collect_daily_for_all_channels
from bot.services.alerts import notify_daily_stats

logger = logging.getLogger()

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    scheduler = AsyncIOScheduler(timezone=MSK_TZ)
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started with tz=%s", MSK_TZ)
    return scheduler


def add_daily_job(bot: Bot) -> None:
    scheduler = start_scheduler()

    async def _job_wrapper() -> None:
        try:
            # Use today's local date for snapshot (at 00:00 job runs for the new day)
            await collect_daily_for_all_channels(datetime.now(tz=MSK_TZ))
        except Exception:
            logger.exception("Daily collection job failed")

    # Run at 23:45 MSK daily
    trigger = CronTrigger(hour=23, minute=45, timezone=MSK_TZ)
    scheduler.add_job(_job_wrapper, trigger, id="daily_collect", replace_existing=True)
    logger.info("Daily job scheduled at 23:45 MSK")

    async def _notify_job() -> None:
        try:
            await notify_daily_stats(bot)
        except Exception:
            logger.exception("Daily stats notify job failed")

    notify_trigger = CronTrigger(hour=9, minute=0, timezone=MSK_TZ)
    scheduler.add_job(_notify_job, notify_trigger, id="daily_notify_stats", replace_existing=True)
    logger.info("Daily stats notification scheduled at 09:00 MSK")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("Failed to shutdown scheduler")
    finally:
        _scheduler = None


