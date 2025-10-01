from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот учёта доходов/расходов. Используйте /add для добавления операции, /help для справки."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Шаги: тип операции → каналы или общая → категория → сумма → подтверждение. /cancel для отмены."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    await message.answer("Операция отменена.")
