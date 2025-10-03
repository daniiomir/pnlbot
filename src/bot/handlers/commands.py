from __future__ import annotations

import logging
import os
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.channels import channels_inline_menu_kb
from bot.keyboards.common import options_menu_kb
from bot.db.models import User
from bot.services.time import now_msk
from bot.services.channel_stats import collect_daily_for_all_channels
from bot.db.base import session_scope
from bot.db.models import Channel, ChannelDailySnapshot, PostSnapshot, ChannelDailyChurn
from sqlalchemy import func
from bot.services.alerts import build_stats_report_text
from datetime import timedelta, timezone
 
logger = logging.getLogger()
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        (
            "<b>👋 Привет!</b>\n"
            "Я помогу учитывать доходы/расходы по каналам и смотреть охваты.\n\n"
            "<b>⚡ Быстрый старт</b>\n"
            "• <b>/in</b> — добавить доход (сразу к выбору категории)\n"
            "• <b>/out</b> — добавить расход (сразу к выбору категории)\n\n"
            "<b>🧭 Полный сценарий</b>\n"
            "• <b>/add</b> — добавить операцию пошагово\n"
            "• <b>/cancel</b> — отменить текущую операцию\n"
            "• <b>/help</b> — краткая справка\n\n"
            "<b>📢 Каналы</b>\n"
            "• <b>/channels</b> — меню управления каналами\n\n"
            "<b>📊 Статистика</b>\n"
            "• <b>/collect_now</b> — собрать метрики сейчас\n"
            "• <b>/stats</b> — охваты за 24/48/72ч, средние просмотры и ER\n\n"
            "<b>💡 Подсказки</b>\n"
            "• На шаге каналов — мультивыбор.\n"
            "• Сумму вводите с копейками (напр.: 1200.50 или 1 200,50).\n"
            "• В конце можно добавить ссылку на чек и комментарий."
        ),
        reply_markup=channels_inline_menu_kb(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Шаги: тип операции → каналы или общая → категория → сумма → подтверждение. /cancel для отмены."
    )


@router.callback_query(lambda c: c.data == "options:menu")
async def options_menu(cb):
    uid = cb.from_user.id if cb.from_user else None
    if uid is None:
        await cb.answer("Техническая ошибка", show_alert=True)
        return
    with session_scope() as s:
        user = s.query(User).filter(User.tg_user_id == uid).one_or_none()
        notify = bool(getattr(user, "notify_daily_stats", False)) if user else False
    await cb.message.edit_text("Опции:", reply_markup=options_menu_kb(notify_on=notify))
    await cb.answer()


@router.callback_query(lambda c: c.data == "options:toggle_notify")
async def options_toggle_notify(cb):
    uid = cb.from_user.id if cb.from_user else None
    if uid is None:
        await cb.answer("Техническая ошибка", show_alert=True)
        return
    with session_scope() as s:
        user = s.query(User).filter(User.tg_user_id == uid).one_or_none()
        if user is None:
            await cb.answer("Пользователь не найден", show_alert=True)
            return
        user.notify_daily_stats = not bool(user.notify_daily_stats)
        s.flush()
        new_state = bool(user.notify_daily_stats)
    await cb.message.edit_reply_markup(reply_markup=options_menu_kb(notify_on=new_state))
    await cb.answer("Оповещение: " + ("включено" if new_state else "выключено"))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    await message.answer("Операция отменена.")


@router.message(Command("collect_now"))
async def cmd_collect_now(message: Message) -> None:
    await message.answer("Сбор статистики запущен…")
    try:
        res = await collect_daily_for_all_channels(now_msk())
        await message.answer(
            "Сбор статистики завершён.\n"
            f"Каналов: {res['channels']}\n"
            f"Дней: +{res['daily_inserted']}/~{res['daily_updated']}\n"
            f"Постов: +{res['posts_inserted']}/~{res['posts_updated']}"
        )
    except Exception as exc:
        logger.exception("collect_now failed: %s", exc)
        echo = os.environ.get("ECHO_ERRORS_TO_USER", "0").strip() in ("1", "true", "True")
        if echo:
            await message.answer(f"Ошибка: {type(exc).__name__}: {exc}")
        else:
            await message.answer("Ошибка при сборе статистики. См. логи.")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    text = await build_stats_report_text()
    await message.answer(text, parse_mode="HTML")



