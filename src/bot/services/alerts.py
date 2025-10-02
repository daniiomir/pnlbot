from __future__ import annotations

import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, user_ids: list[int], text: str) -> None:
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
        except Exception:
            logger.exception("Failed to send alert to %s", uid)


