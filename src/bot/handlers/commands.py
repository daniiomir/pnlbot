from __future__ import annotations

import logging
import os
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.channels import channels_inline_menu_kb
from bot.keyboards.common import options_menu_kb
from bot.db.models import User
from bot.services.time import now_msk
from bot.services.channel_stats import collect_daily_for_all_channels
from bot.db.base import session_scope
from bot.db.models import Channel
from sqlalchemy import func
from bot.services.alerts import build_stats_report_text
from datetime import timedelta
from bot.types.enums import OperationType
from bot.db.models import Operation, OperationChannel
 
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
            "• <b>/out</b> — добавить расход (сразу к выбору категории)\n"
            "• <b>/invest</b> — добавить личные вложения (сразу выбор категории)\n\n"
            "<b>🧭 Полный сценарий</b>\n"
            "• <b>/add</b> — добавить операцию пошагово\n"
            "• <b>/cancel</b> — отменить текущую операцию\n"
            "• <b>/help</b> — краткая справка\n\n"
            "<b>📢 Каналы</b>\n"
            "• <b>/channels</b> — меню управления каналами\n\n"
            "<b>📊 Статистика</b>\n"
            "• <b>/stats</b> — охваты за 24/48/72ч, средние просмотры и ER\n\n"
            "<b>💵 Финансы</b>\n"
            "• <b>/cashflow</b> — доходы/расходы за неделю и месяц, CPS (с вычетом отписок)\n\n"
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



@router.message(Command("cashflow"))
async def cmd_cashflow(message: Message) -> None:
    now_local = now_msk()
    # Week: Mon 00:00 — next Mon 00:00 (MSK)
    week_start = (now_local - timedelta(days=(now_local.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Month: first day 00:00 — first day of next month 00:00 (MSK)
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_next = (month_start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def fmt_money(kop: int) -> str:
        total_kop = int(kop)
        rub_abs = abs(total_kop) // 100
        cnt_abs = abs(total_kop) % 100
        sign = "" if total_kop >= 0 else "-"
        return f"{sign}{rub_abs:,}.{cnt_abs:02d} ₽".replace(",", " ")

    def _sum_ops_amount_kop(s, ch_ids: list[int], *, op_type: int | None = None, category_id: int | None = None, start=None, end=None) -> int:
        # Sum for channel-linked operations (deduplicated by operation)
        base = (
            s.query(
                Operation.id.label("op_id"),
                func.max(Operation.amount_kop).label("amt"),
            )
            .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
            .filter(
                Operation.is_general.is_(False),
                OperationChannel.c.channel_id.in_(ch_ids),
            )
        )
        if start is not None and end is not None:
            base = base.filter(Operation.created_at >= start, Operation.created_at < end)
        if op_type is not None:
            base = base.filter(Operation.op_type == op_type)
        if category_id is not None:
            base = base.filter(Operation.category_id == category_id)
        sub = base.group_by(Operation.id).subquery()
        ch_total = s.query(func.coalesce(func.sum(sub.c.amt), 0)).scalar() or 0

        # Sum for general operations (not linked to channels)
        gen_q = s.query(func.coalesce(func.sum(Operation.amount_kop), 0)).filter(
            Operation.is_general.is_(True),
        )
        if start is not None and end is not None:
            gen_q = gen_q.filter(Operation.created_at >= start, Operation.created_at < end)
        if op_type is not None:
            gen_q = gen_q.filter(Operation.op_type == op_type)
        if category_id is not None:
            gen_q = gen_q.filter(Operation.category_id == category_id)
        gen_total = gen_q.scalar() or 0

        return int(ch_total or 0) + int(gen_total or 0)

    def build_period(fin_start, fin_end, header: str) -> str:
        with session_scope() as s:
            channels = (
                s.query(Channel)
                .filter(Channel.is_active.is_(True))
                .order_by(Channel.created_at.desc())
                .all()
            )
            if not channels:
                return f"<b>{header}</b>\nКаналов нет."
            ch_ids = [c.id for c in channels]

            income_kop = _sum_ops_amount_kop(s, ch_ids, op_type=OperationType.INCOME.value, start=fin_start, end=fin_end)
            expense_kop = _sum_ops_amount_kop(s, ch_ids, op_type=OperationType.EXPENSE.value, start=fin_start, end=fin_end)

            personal_invest_kop = int(_sum_ops_amount_kop(s, ch_ids, op_type=OperationType.PERSONAL_INVEST.value, start=fin_start, end=fin_end) or 0)

            op_expense_kop = int(expense_kop)
            profit_kop = int(income_kop) - int(op_expense_kop)

            lines: list[str] = []
            lines.append(f"<b>{header}</b>")
            lines.append(f"Вложения: {fmt_money(int(personal_invest_kop))}")
            lines.append(f"Расходы: {fmt_money(int(op_expense_kop))}")
            lines.append(f"Доходы: {fmt_money(int(income_kop))}")
            lines.append(f"Чистая прибыль: {fmt_money(int(profit_kop))}")
            return "\n".join(lines)

    def build_overall() -> str:
        with session_scope() as s:
            channels = (
                s.query(Channel)
                .filter(Channel.is_active.is_(True))
                .order_by(Channel.created_at.desc())
                .all()
            )
            if not channels:
                return "<b>ОБЩЕЕ</b>\nКаналов нет."
            ch_ids = [c.id for c in channels]

            income_all = _sum_ops_amount_kop(s, ch_ids, op_type=OperationType.INCOME.value)
            expense_all = _sum_ops_amount_kop(s, ch_ids, op_type=OperationType.EXPENSE.value)

            personal_invest_all = int(_sum_ops_amount_kop(s, ch_ids, op_type=OperationType.PERSONAL_INVEST.value) or 0)

            op_expense_all = int(expense_all)

            cash_left = int(personal_invest_all) - int(op_expense_all)
            net_profit = int(income_all) - int(op_expense_all)
            cash_with_income = int(personal_invest_all) + int(income_all) - int(op_expense_all)

            lines: list[str] = []
            lines.append("<b>ОБЩЕЕ</b>")
            lines.append(f"Вложения всего: {fmt_money(int(personal_invest_all))}")
            lines.append(f"Расходы всего: {fmt_money(int(op_expense_all))}")
            lines.append(f"Доходы всего: {fmt_money(int(income_all))}")
            lines.append(f"Остаток средств: {fmt_money(int(cash_left))}")
            lines.append(f"Чистая прибыль: {fmt_money(int(net_profit))}")
            lines.append(f"Остаток с учётом доходов: {fmt_money(int(cash_with_income))}")
            return "\n".join(lines)

    def _fmt_date(d) -> str:
        try:
            return d.strftime("%d.%m.%Y")
        except Exception:
            return str(d)

    week_label = f"Текущая неделя ({_fmt_date(week_start.date())}–{_fmt_date((week_end - timedelta(days=1)).date())})"
    month_label = f"Текущий месяц ({_fmt_date(month_start.date())}–{_fmt_date((month_next - timedelta(days=1)).date())})"

    overall_block = build_overall()
    month_block = build_period(month_start, month_next, month_label)
    week_block = build_period(week_start, week_end, week_label)

    await message.answer(
        f"{overall_block}\n\n{month_block}\n\n{week_block}",
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "cashflow:how")
async def cashflow_how(cb):
    text = (
        "<b>Как считается Cashflow</b>\n\n"
        "<b>Финансовые итоги периода</b>\n"
        "• Доход = сумма доходов за период.\n"
        "• Расходы (без личных вложений) = все расходы − личные вложения.\n"
        "• Личные вложения = сумма личных вложений владельца.\n"
        "• Маржа = Доход − Расходы (без личных вложений).\n"
        "• Маржинальность = (Маржа / Доход) × 100%.\n\n"
        "<b>Реклама и CPS</b>\n"
        "• Закупка рекламы = расходы на рекламу.\n"
        "• Вступления/Отписки = количество новых подписчиков / отписок.\n"
        "• Чистый прирост = Вступления − Отписки.\n"
        "• CPS (расход на 1 чистого) = Закупка рекламы / Чистый прирост (если > 0).\n\n"
        "<b>Доп. метрики</b>\n"
        "• Доход/пост = Доход / число постов за период.\n"
        "• Расход/пост = Расходы (без личных) / число постов.\n"
        "• RPM = Доход / (Просмотры / 1000).\n"
        "• CPM = Расходы (без личных) / (Просмотры / 1000).\n"
        "• ARPU = Доход / Среднее число подписчиков за период.\n"
        "• ROMI = Доход / Закупка рекламы.\n\n"
        "<b>Общие правила</b>\n"
        "• Учитываются операции по каналам и общие (если есть).\n"
        "• Неделя/месяц — календарные периоды (MSK).\n\n"
        "<b>Общий баланс средств</b>\n"
        "• За всё время: все доходы − все расходы."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Главное меню", callback_data="main:menu")]
        ]
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@router.callback_query(lambda c: c.data == "main:menu")
async def main_menu_cb(cb):
    await cb.message.answer("Главное меню", reply_markup=channels_inline_menu_kb())
    await cb.answer()


