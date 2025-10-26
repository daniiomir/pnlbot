from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.base import session_scope
from bot.db.models import Channel, User, Operation, Category, OperationChannel
from bot.keyboards.channels import channels_main_menu_kb, channel_actions_kb, channels_inline_menu_kb
from bot.keyboards.common import back_to_main_menu_kb
from bot.services.time import now_msk
from bot.services.channel_stats import collect_for_channel
from bot.types.enums import OperationType

logger = logging.getLogger()

router = Router()


@router.message(Command("channels"))
async def cmd_channels(message: Message) -> None:
    await message.answer("Управление каналами:", reply_markup=channels_inline_menu_kb())


@router.message(F.text == "➕ Добавить канал")
async def ask_forward(message: Message) -> None:
    await message.answer(
        "Перешлите сюда любой пост из канала, который хотите добавить.\n"
        "Если канал приватный — добавьте нашего тех. аккаунта (Telethon session) в участники и назначьте <b>администратором</b> для расширенной статистики (подписки/отписки).",
        parse_mode="HTML",
    )


@router.message(F.forward_from_chat)
async def handle_forwarded_post(message: Message) -> None:
    fwd = message.forward_from_chat
    if fwd is None:
        return
    tg_chat_id = fwd.id
    title = fwd.title
    username = fwd.username

    added_by_user_id = message.from_user.id if message.from_user else None
    with session_scope() as s:
        existing = s.query(Channel).filter(Channel.tg_chat_id == tg_chat_id).one_or_none()
        if existing:
            existing.title = existing.title or title
            existing.username = existing.username or username
            existing.is_active = True
            existing.last_error = None
            existing.last_success_at = now_msk()
            s.flush()
            ch_id = existing.id
        else:
            ch = Channel(
                tg_chat_id=tg_chat_id,
                title=title,
                username=username,
                created_at=now_msk(),
                is_active=True,
                last_success_at=None,
                last_error=None,
                added_by_user_id=None,
            )
            # Resolve added_by_user_id to DB user
            if added_by_user_id is not None:
                user = s.query(User).filter(User.tg_user_id == added_by_user_id).one_or_none()
                if user is not None:
                    ch.added_by_user_id = user.id
            s.add(ch)
            s.flush()
            ch_id = ch.id

    # Trigger immediate stats collection for this channel
    try:
        res = await collect_for_channel(ch_id, tg_chat_id, now_msk())
        await message.answer(
            f"Канал добавлен: {title or username or tg_chat_id}\n"
            f"Сбор выполнен: подписчики и посты (72ч).\n"
            f"⚠️ Назначьте наш тех. аккаунт Telethon <b>администратором</b> канала, иначе метрики подписок/отписок будут недоступны.",
            parse_mode="HTML",
            reply_markup=channel_actions_kb(ch_id),
        )
    except Exception:
        logger.exception("Immediate collect failed for channel %s", tg_chat_id)
        await message.answer(
            f"Канал добавлен: {title or username or tg_chat_id}\n"
            "Не удалось сразу собрать статистику (см. логи).\n"
            "⚠️ Назначьте наш тех. аккаунт Telethon <b>администратором</b> канала для расширенной статистики.",
            parse_mode="HTML",
            reply_markup=channel_actions_kb(ch_id),
        )


@router.message(F.text == "📋 Список каналов")
async def list_channels(message: Message) -> None:
    with session_scope() as s:
        rows = (
            s.query(Channel.id, Channel.title, Channel.username, Channel.tg_chat_id, Channel.is_active)
            .order_by(Channel.id.desc())
            .limit(20)
            .all()
        )
    if not rows:
        await message.answer("Список каналов пуст. Нажмите ‘Добавить канал’.")
        return
    for ch_id, title, username, tg_chat_id, is_active in rows:
        text = f"{title or username or tg_chat_id} — {'активен' if is_active else 'на паузе'}"
        await message.answer(text, reply_markup=channel_actions_kb(ch_id))


# Inline callbacks from start inline menu
@router.callback_query(F.data == "channels:add")
async def inline_add_channel(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "Перешлите сюда любой пост из канала, который хотите добавить.\n"
        "Если канал приватный — добавьте нашего тех. аккаунта (Telethon session) в участники и назначьте <b>администратором</b> для расширенной статистики (подписки/отписки).",
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(F.data == "channels:list")
async def inline_list_channels(cb: CallbackQuery) -> None:
    with session_scope() as s:
        rows = (
            s.query(Channel.id, Channel.title, Channel.username, Channel.tg_chat_id, Channel.is_active)
            .order_by(Channel.id.desc())
            .limit(20)
            .all()
        )
    if not rows:
        await cb.message.answer("Список каналов пуст. Нажмите ‘Добавить канал’.")
        await cb.answer()
        return
    for ch_id, title, username, tg_chat_id, is_active in rows:
        text = f"{title or username or tg_chat_id} — {'активен' if is_active else 'на паузе'}"
        await cb.message.answer(text, reply_markup=channel_actions_kb(ch_id))
    await cb.answer()


@router.callback_query(F.data == "operations:history")
async def inline_operations_history(cb: CallbackQuery) -> None:
    with session_scope() as s:
        # fetch last 20 operations globally
        rows = (
            s.query(
                Operation.id,
                Operation.created_at,
                Operation.op_type,
                Operation.category_id,
                Operation.amount_kop,
                Operation.is_general,
                Operation.receipt_url,
                Operation.comment,
            )
            .order_by(Operation.id.desc())
            .limit(20)
            .all()
        )
        cat_by_id = {c.id: c for c in s.query(Category).all()}
        # build map of operation_id -> channel ids
        op_ids = [r.id for r in rows]
        ch_map: dict[int, list[int]] = {}
        if op_ids:
            res = s.execute(
                OperationChannel.select().where(OperationChannel.c.operation_id.in_(op_ids))
            )
            for op_id, ch_id in res:
                ch_map.setdefault(int(op_id), []).append(int(ch_id))
        # fetch channel titles for all involved ids
        all_ch_ids = {cid for ids in ch_map.values() for cid in ids}
        ch_title_by_id: dict[int, str] = {}
        if all_ch_ids:
            ch_rows = (
                s.query(Channel.id, Channel.title, Channel.username, Channel.tg_chat_id)
                .filter(Channel.id.in_(list(all_ch_ids)))
                .all()
            )
            ch_title_by_id = {
                row.id: (row.title or row.username or str(row.tg_chat_id)) for row in ch_rows
            }
        # prepare text
        lines: list[str] = ["Последние 20 транзакций:"]
        for r in rows:
            if r.op_type == OperationType.INCOME.value:
                op_type_txt = "Доход"
            elif r.op_type == OperationType.PERSONAL_INVEST.value:
                op_type_txt = "Личные вложения"
            else:
                op_type_txt = "Расход"
            cat_name = cat_by_id.get(r.category_id).name if cat_by_id.get(r.category_id) else str(r.category_id)
            rub = int(r.amount_kop) // 100
            if r.is_general:
                channels_txt = "общая"
            else:
                ch_ids = ch_map.get(r.id, [])
                if ch_ids:
                    names = [ch_title_by_id.get(cid, str(cid)) for cid in ch_ids]
                    channels_txt = ", ".join(names)
                else:
                    channels_txt = "—"
            dt = r.created_at
            try:
                dt_txt = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_txt = str(dt)
            lines.append(f"{dt_txt} · {op_type_txt} · {cat_name} · {rub} RUB · {channels_txt}")
            if r.receipt_url:
                lines.append(f"  Чек: {r.receipt_url}")
            if r.comment:
                lines.append(f"  Комментарий: {r.comment}")
            lines.append("")

    if len(lines) == 1:
        lines.append("Пока нет операций.")
    await cb.message.edit_text("\n".join(lines), reply_markup=back_to_main_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "channels:menu")
async def inline_main_menu(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
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
    await cb.answer()


@router.callback_query(F.data.startswith("ch_toggle:"))
async def toggle_channel(cb: CallbackQuery) -> None:
    channel_id = int(cb.data.split(":", 1)[1])
    with session_scope() as s:
        ch = s.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if not ch:
            await cb.answer("Канал не найден", show_alert=True)
            return
        ch.is_active = not ch.is_active
        s.flush()
        await cb.answer("Готово")
        await cb.message.edit_text(
            f"{ch.title or ch.username or ch.tg_chat_id} — {'активен' if ch.is_active else 'на паузе'}"
        )


@router.callback_query(F.data.startswith("ch_delete:"))
async def delete_channel(cb: CallbackQuery) -> None:
    channel_id = int(cb.data.split(":", 1)[1])
    with session_scope() as s:
        ch = s.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if not ch:
            await cb.answer("Канал не найден", show_alert=True)
            return
        ch.is_active = False
        ch.last_error = "deleted_by_user"
        s.flush()
    await cb.answer("Удалено")
    await cb.message.edit_text("Канал удалён/деактивирован")


