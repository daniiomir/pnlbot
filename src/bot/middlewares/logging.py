from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        chat_id: int | None = None
        payload: str | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id if event.chat else None
            payload = event.text or event.caption
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.message.chat.id if event.message and event.message.chat else None
            payload = event.data

        state: FSMContext | None = data.get("state")  # aiogram injects if available
        state_name: str | None = None
        if state is not None:
            try:
                cur = await state.get_state()
                state_name = cur
            except Exception:
                state_name = None

        logger.info(
            "update event=%s user_id=%s chat_id=%s state=%s payload=%s",
            event.__class__.__name__,
            user_id,
            chat_id,
            state_name,
            (payload or ""),
        )
        return await handler(event, data)
