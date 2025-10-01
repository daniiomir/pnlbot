from __future__ import annotations

import asyncio
import time
from typing import Callable, Awaitable, Any, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, min_interval_seconds: float = 0.7):
        self.min_interval = min_interval_seconds
        self._last_call_by_user: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None:
            now = time.monotonic()
            last = self._last_call_by_user.get(user_id, 0.0)
            delta = now - last
            if delta < self.min_interval:
                await asyncio.sleep(self.min_interval - delta)
            self._last_call_by_user[user_id] = time.monotonic()

        return await handler(event, data)
