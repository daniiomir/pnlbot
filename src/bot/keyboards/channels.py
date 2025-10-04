from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def channels_main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить канал")],
            [KeyboardButton(text="📋 Список каналов")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление каналами",
    )


def channel_actions_kb(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пауза/Возобновить", callback_data=f"ch_toggle:{channel_id}")],
            [InlineKeyboardButton(text="Удалить", callback_data=f"ch_delete:{channel_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="channels:menu")],
        ]
    )

def channels_inline_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels:add")],
            [InlineKeyboardButton(text="📋 Список каналов", callback_data="channels:list")],
            [InlineKeyboardButton(text="🧾 История транзакций", callback_data="operations:history")],
            [InlineKeyboardButton(text="⚙️ Опции", callback_data="options:menu")],
        ]
    )


