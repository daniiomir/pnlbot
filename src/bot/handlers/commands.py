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
from bot.types.enums import OperationType
from bot.db.models import Operation, OperationChannel, Category
 
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
    # Current calendar week (Mon-Sun) and month in MSK
    week_start = (now_local - timedelta(days=(now_local.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # For month_end, add 32 days to guarantee next month, then set day=1 at 00:00
    month_next = (month_start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def build_period(fin_start, fin_end, label: str) -> str:
        with session_scope() as s:
            # Active channels
            channels = (
                s.query(Channel)
                .filter(Channel.is_active.is_(True))
                .order_by(Channel.created_at.desc())
                .all()
            )
            if not channels:
                return f"<b>{label}</b>\nКаналов нет."

            ch_ids = [c.id for c in channels]

            # Finance: sum income/expense for operations linked to channels (exclude is_general)
            # Join via OperationChannel; filter by created_at in [start, end)
            income_kop = (
                s.query(func.coalesce(func.sum(Operation.amount_kop), 0))
                .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
                .filter(
                    Operation.op_type == OperationType.INCOME.value,
                    Operation.is_general.is_(False),
                    Operation.created_at >= fin_start,
                    Operation.created_at < fin_end,
                    OperationChannel.c.channel_id.in_(ch_ids),
                )
                .scalar()
            ) or 0
            income_kop = int(income_kop or 0)

            expense_kop = (
                s.query(func.coalesce(func.sum(Operation.amount_kop), 0))
                .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
                .filter(
                    Operation.op_type == OperationType.EXPENSE.value,
                    Operation.is_general.is_(False),
                    Operation.created_at >= fin_start,
                    Operation.created_at < fin_end,
                    OperationChannel.c.channel_id.in_(ch_ids),
                )
                .scalar()
            ) or 0
            expense_kop = int(expense_kop or 0)

            # Ad purchase expenses for CPS denominator
            ad_purchase_cat = s.query(Category.id).filter(Category.code == "ad_purchase").one_or_none()
            ad_purchase_cat_id = ad_purchase_cat[0] if ad_purchase_cat else None
            ad_purchase_kop = 0
            if ad_purchase_cat_id is not None:
                ad_purchase_kop = (
                    s.query(func.coalesce(func.sum(Operation.amount_kop), 0))
                    .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
                    .filter(
                        Operation.op_type == OperationType.EXPENSE.value,
                        Operation.category_id == ad_purchase_cat_id,
                        Operation.is_general.is_(False),
                        Operation.created_at >= fin_start,
                        Operation.created_at < fin_end,
                        OperationChannel.c.channel_id.in_(ch_ids),
                    )
                    .scalar()
                ) or 0
            ad_purchase_kop = int(ad_purchase_kop or 0)

            # Churn: sum joins/leaves by date range inclusive using ChannelDailyChurn
            start_date = fin_start.date()
            end_date = (fin_end - timedelta(seconds=1)).date()
            joins_sum, leaves_sum = (
                s.query(
                    func.coalesce(func.sum(ChannelDailyChurn.joins_count), 0),
                    func.coalesce(func.sum(ChannelDailyChurn.leaves_count), 0),
                )
                .filter(
                    ChannelDailyChurn.channel_id.in_(ch_ids),
                    ChannelDailyChurn.snapshot_date >= start_date,
                    ChannelDailyChurn.snapshot_date <= end_date,
                )
                .one()
            )
            net_new = int(joins_sum or 0) - int(leaves_sum or 0)

            profit_kop = int(income_kop) - int(expense_kop)

            # Posts and views for period
            # Count posts by posted_at; sum views from PostSnapshot within date range
            # Use local dates inclusive for PostSnapshot.snapshot_date and posted_at window
            start_utc = fin_start.astimezone(timezone.utc)
            end_utc = fin_end.astimezone(timezone.utc)
            posts_count = (
                s.query(func.count(PostSnapshot.id))
                .filter(
                    PostSnapshot.channel_id.in_(ch_ids),
                    PostSnapshot.posted_at >= start_utc,
                    PostSnapshot.posted_at < end_utc,
                )
                .scalar()
            ) or 0
            posts_count = int(posts_count or 0)
            views_sum = (
                s.query(func.coalesce(func.sum(PostSnapshot.views), 0))
                .filter(
                    PostSnapshot.channel_id.in_(ch_ids),
                    PostSnapshot.posted_at >= start_utc,
                    PostSnapshot.posted_at < end_utc,
                )
                .scalar()
            ) or 0
            views_sum = int(views_sum or 0)

            # Average subscribers over period using ChannelDailySnapshot
            start_date = fin_start.date()
            end_date = (fin_end - timedelta(seconds=1)).date()
            avg_subs = (
                s.query(func.avg(ChannelDailySnapshot.subscribers_count))
                .filter(
                    ChannelDailySnapshot.channel_id.in_(ch_ids),
                    ChannelDailySnapshot.snapshot_date >= start_date,
                    ChannelDailySnapshot.snapshot_date <= end_date,
                )
                .scalar()
            ) or 0
            avg_subs = int(avg_subs or 0)

            def fmt_money(kop: int) -> str:
                total_kop = int(kop)
                rub_abs = abs(total_kop) // 100
                cnt_abs = abs(total_kop) % 100
                sign = "" if total_kop >= 0 else "-"
                return f"{sign}{rub_abs:,}.{cnt_abs:02d} ₽".replace(",", " ")

            # CPS with net joins: ad purchase spend / max(net_new,1) to avoid division by zero.
            cps_txt = "-"
            if ad_purchase_kop and net_new > 0:
                cps_rub = (ad_purchase_kop / 100.0) / float(net_new)
                cps_txt = f"{cps_rub:,.2f} ₽".replace(",", " ")

            # Маржинальность: прибыль/доход
            margin_txt = "-"
            if income_kop:
                margin = (float(profit_kop) / float(income_kop)) * 100.0
                margin_txt = f"{margin:.1f}%"

            lines: list[str] = []
            lines.append(f"<b>{label}</b>")
            lines.append(f"Доход: {fmt_money(int(income_kop))}")
            lines.append(f"Расходы: {fmt_money(int(expense_kop))}")
            lines.append(f"Прибыль: {fmt_money(int(profit_kop))}")
            lines.append(f"Маржинальность: {margin_txt}")
            # Additional helpful items
            lines.append(f"Закупка рекламы: {fmt_money(int(ad_purchase_kop))}")
            lines.append(f"Вступления: {int(joins_sum or 0)}, Отписки: {int(leaves_sum or 0)}, Чистый прирост: {net_new}")
            lines.append(f"CPS (расход на 1 чистого подписчика): {cps_txt}")

            # Extended metrics
            # Доход/расход на пост
            income_per_post_txt = "-"
            expense_per_post_txt = "-"
            if posts_count > 0:
                income_per_post_txt = f"{(income_kop/100.0)/posts_count:,.2f} ₽".replace(",", " ")
                expense_per_post_txt = f"{(expense_kop/100.0)/posts_count:,.2f} ₽".replace(",", " ")
            # RPM/CPM (на 1000 просмотров)
            rpm_txt = "-"
            cpm_txt = "-"
            if views_sum and views_sum > 0:
                rpm_txt = f"{(income_kop/100.0)/(views_sum/1000.0):,.2f} ₽".replace(",", " ")
                cpm_txt = f"{(expense_kop/100.0)/(views_sum/1000.0):,.2f} ₽".replace(",", " ")
            # ARPU (доход на средн. подписчика за период)
            arpu_txt = "-"
            if avg_subs and avg_subs > 0:
                arpu_txt = f"{(income_kop/100.0)/float(avg_subs):,.2f} ₽".replace(",", " ")
            # ROMI (доход/расходы на рекламу)
            romi_txt = "-"
            if ad_purchase_kop and ad_purchase_kop > 0:
                romi = (float(income_kop) / float(ad_purchase_kop))
                romi_txt = f"{romi:,.2f}x".replace(",", " ")

            lines.append("")
            lines.append("— Доп. метрики —")
            lines.append(f"Доход/пост: {income_per_post_txt}")
            lines.append(f"Расход/пост: {expense_per_post_txt}")
            lines.append(f"RPM (доход/1000 просмотров): {rpm_txt}")
            lines.append(f"CPM (расход/1000 просмотров): {cpm_txt}")
            lines.append(f"ARPU (доход на 1 подписчика): {arpu_txt}")
            lines.append(f"ROMI (доход/закупка рекламы): {romi_txt}")
            return "\n".join(lines)

    def _fmt_date(d) -> str:
        try:
            return d.strftime("%d.%m.%Y")
        except Exception:
            return str(d)

    week_start_d = week_start.date()
    week_end_d = (week_end - timedelta(days=1)).date()
    month_start_d = month_start.date()
    month_end_d = (month_next - timedelta(days=1)).date()

    week_label = f"💰 Финансы — неделя ({_fmt_date(week_start_d)}–{_fmt_date(week_end_d)})"
    month_label = f"💰 Финансы — месяц ({_fmt_date(month_start_d)}–{_fmt_date(month_end_d)})"

    week_block = build_period(week_start, week_end, week_label)
    month_block = build_period(month_start, month_next, month_label)

    # Общий баланс средств (за всё время по активным каналам)
    with session_scope() as s:
        channels = (
            s.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.desc())
            .all()
        )
        ch_ids = [c.id for c in channels]
        income_all = 0
        expense_all = 0
        if ch_ids:
            income_all = (
                s.query(func.coalesce(func.sum(Operation.amount_kop), 0))
                .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
                .filter(
                    Operation.op_type == OperationType.INCOME.value,
                    Operation.is_general.is_(False),
                    OperationChannel.c.channel_id.in_(ch_ids),
                )
                .scalar()
            ) or 0
            expense_all = (
                s.query(func.coalesce(func.sum(Operation.amount_kop), 0))
                .join(OperationChannel, OperationChannel.c.operation_id == Operation.id)
                .filter(
                    Operation.op_type == OperationType.EXPENSE.value,
                    Operation.is_general.is_(False),
                    OperationChannel.c.channel_id.in_(ch_ids),
                )
                .scalar()
            ) or 0
        income_all = int(income_all or 0)
        expense_all = int(expense_all or 0)
        balance_all = income_all - expense_all

        def _fmt_money_total(kop: int) -> str:
            total_kop = int(kop)
            rub_abs = abs(total_kop) // 100
            cnt_abs = abs(total_kop) % 100
            sign = "" if total_kop >= 0 else "-"
            return f"{sign}{rub_abs:,}.{cnt_abs:02d} ₽".replace(",", " ")

    balance_block = f"💼 Общий баланс средств: {_fmt_money_total(balance_all)}"

    await message.answer(f"{week_block}\n\n{month_block}\n\n{balance_block}", parse_mode="HTML")


