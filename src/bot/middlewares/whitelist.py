from __future__ import annotations

import logging
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.settings import Settings
from bot.db.base import session_scope
from bot.db.models import User
from bot.services.time import now_msk

logger = logging.getLogger()


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user_id: int | None = None
        message: Message | None = None
        if isinstance(event, Message):
            message = event
            if message.chat.type != "private":
                return
            if message.from_user:
                from_user_id = message.from_user.id
        elif isinstance(event, CallbackQuery):
            if event.message and event.message.chat and event.message.chat.type != "private":
                return
            if event.from_user:
                from_user_id = event.from_user.id

        if from_user_id is None:
            return await handler(event, data)

        if from_user_id not in self.settings.whitelist_user_ids:
            if message:
                await message.answer("Доступ запрещён. Обратитесь к администратору.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён", show_alert=True)
            logger.info("Rejected non-whitelisted user: %s", from_user_id)
            return

        try:
            with session_scope() as s:
                user = s.query(User).filter(User.tg_user_id == from_user_id).one_or_none()
                if user is None:
                    user = User(
                        tg_user_id=from_user_id,
                        first_name=getattr(getattr(event, "from_user", None), "first_name", None),
                        last_name=getattr(getattr(event, "from_user", None), "last_name", None),
                        username=getattr(getattr(event, "from_user", None), "username", None),
                        created_at=now_msk(),
                    )
                    s.add(user)
        except Exception:
            logger.exception("Failed to upsert user")

        return await handler(event, data)
