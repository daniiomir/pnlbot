from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я помогу учитывать доходы и расходы по каналам.\n\n"
        "Быстрый старт:\n"
        "• /in — добавить доход (сразу к выбору категории)\n"
        "• /out — добавить расход (сразу к выбору категории)\n\n"
        "Полный сценарий:\n"
        "• /add — добавить операцию пошагово\n"
        "• /cancel — отменить текущую операцию\n"
        "• /help — справка\n\n"
        "Подсказки:\n"
        "• На шаге каналов — мультивыбор.\n"
        "• Сумму можно вводить с копейками (например: 1200.50 или 1 200,50).\n"
        "• В конце можно добавить ссылку на чек и комментарий (по желанию)."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Шаги: тип операции → каналы или общая → категория → сумма → подтверждение. /cancel для отмены."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    await message.answer("Операция отменена.")
