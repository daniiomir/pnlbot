from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, Message, CallbackQuery


logger = logging.getLogger()


class ErrorLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            # Log exception with full traceback using module logger and root logger
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

            state: FSMContext | None = data.get("state")
            state_name: str | None = None
            if state is not None:
                try:
                    state_name = await state.get_state()
                except Exception:
                    state_name = None

            logger.exception(
                "handler error user_id=%s chat_id=%s state=%s payload=%s",
                user_id,
                chat_id,
                state_name,
                (payload or ""),
            )
            # Duplicate to root logger to avoid misconfiguration issues
            import logging as _logging
            _logging.getLogger().exception(
                "handler error (root) user_id=%s chat_id=%s state=%s payload=%s",
                user_id,
                chat_id,
                state_name,
                (payload or ""),
            )
            # Force flush all handlers
            for _h in _logging.getLogger().handlers:
                try:
                    _h.flush()
                except Exception:
                    pass

            # Best-effort user notification, but do not raise further
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("Произошла ошибка. Попробуйте ещё раз.", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("Произошла ошибка. Попробуйте ещё раз.")
            except Exception:
                pass

            return None


