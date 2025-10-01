from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def yes_no_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="cancel")],
        ]
    )


def operation_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Доход", callback_data="op_type:income"),
                InlineKeyboardButton(text="Расход", callback_data="op_type:expense"),
            ]
        ]
    )
