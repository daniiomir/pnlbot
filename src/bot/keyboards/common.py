from __future__ import annotations

from typing import Iterable, Iterable as _Iterable

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


def categories_kb(items: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    # items: (id, name, code)
    rows: list[list[InlineKeyboardButton]] = []
    for cat_id, name, code in items:
        rows.append([InlineKeyboardButton(text=f"{name}", callback_data=f"cat:{cat_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="back:type")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_kb(
    channels: Iterable[tuple[int, str | None]],
    selected_ids: _Iterable[int] | None = None,
    page: int = 1,
) -> InlineKeyboardMarkup:
    # channels: (id, title)
    selected_set = set(selected_ids or [])
    rows: list[list[InlineKeyboardButton]] = []
    for ch_id, title in channels:
        text = title or str(ch_id)
        if ch_id in selected_set:
            text = f"✅ {text}"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"ch:{ch_id}")])
    rows.append([InlineKeyboardButton(text="Без канала (общая)", callback_data="ch_general")])
    rows.append([InlineKeyboardButton(text="Готово", callback_data="ch_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data=callback_data)]]
    )


def options_menu_kb(notify_on: bool) -> InlineKeyboardMarkup:
    toggle_text = "Оповещение: Вкл" if notify_on else "Оповещение: Выкл"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="options:toggle_notify")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="channels:menu")],
        ]
    )


def back_to_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="channels:menu")]]
    )
