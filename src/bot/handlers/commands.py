from __future__ import annotations

import logging
import os
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.channels import channels_inline_menu_kb
from bot.services.time import now_msk
from bot.services.channel_stats import collect_daily_for_all_channels
from bot.db.base import session_scope
from bot.db.models import Channel, ChannelDailySnapshot, PostSnapshot
from sqlalchemy import func
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
    today = now_msk().date()
    now_utc = now_msk().astimezone(timezone.utc)
    horizons = [24, 48, 72]
    with session_scope() as s:
        channels = (
            s.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.desc())
            .limit(20)
            .all()
        )
        if not channels:
            await message.answer("Активных каналов не найдено.")
            return
        lines: list[str] = []
        for ch in channels:
            title = ch.title or ch.username or str(ch.tg_chat_id)
            daily = (
                s.query(ChannelDailySnapshot)
                .filter(
                    ChannelDailySnapshot.channel_id == ch.id,
                    ChannelDailySnapshot.snapshot_date == today,
                )
                .one_or_none()
            )
            subs = daily.subscribers_count if daily else None
            parts: list[str] = [f"{title}", f"👥 {subs if subs is not None else '-'}"]
            for h in horizons:
                start_utc = now_utc - timedelta(hours=h)
                cnt, avg_views = (
                    s.query(
                        func.count(PostSnapshot.id),
                        func.avg(PostSnapshot.views),
                    )
                    .filter(
                        PostSnapshot.channel_id == ch.id,
                        PostSnapshot.snapshot_date == today,
                        PostSnapshot.posted_at >= start_utc,
                        PostSnapshot.posted_at <= now_utc,
                    )
                    .one()
                )
                cnt_int = int(cnt or 0)
                avg_int = int((avg_views or 0))
                er_txt = "-"
                if subs and subs > 0 and avg_views is not None:
                    er = (float(avg_views) / float(subs)) * 100.0
                    er_txt = f"{er:.1f}%"
                parts.append(f"{h}ч: 📝 {cnt_int} | 👀 {avg_int} | ER {er_txt}")
            lines.append("\n".join(parts))
        await message.answer("\n\n".join(lines))



