from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.exc import IntegrityError

from bot.keyboards.common import operation_type_kb, yes_no_kb, categories_kb, channels_kb, skip_kb
from bot.types.enums import OperationType, INCOME_CATEGORY_CODES, EXPENSE_CATEGORY_CODES
from bot.services.parsing import parse_amount_rub_to_kop, AmountParseError
from bot.services.time import now_msk
from bot.services.dedup import build_dedup_hash
from bot.db.base import session_scope
from bot.db.models import Category, Channel, Operation, OperationChannel, User

logger = logging.getLogger()

router = Router()


class AddOpStates(StatesGroup):
    choosing_type = State()
    choosing_channels = State()
    choosing_category = State()
    entering_reason = State()
    entering_amount = State()
    entering_receipt = State()
    entering_comment = State()
    confirming = State()


@dataclass
class AddOpData:
    op_type: int | None = None
    is_general: bool = False
    channel_ids: List[int] | None = None
    category_id: int | None = None
    category_code: str | None = None
    free_text_reason: str | None = None
    receipt_url: str | None = None
    comment: str | None = None
    amount_kop: int | None = None

def _format_channel_titles(channel_ids: list[int]) -> str:
    if not channel_ids:
        return "—"
    with session_scope() as s:
        q = s.query(Channel).filter(Channel.id.in_(channel_ids)).all()
        by_id: dict[int, str] = {ch.id: (ch.title or str(ch.id)) for ch in q}
    titles = [by_id.get(cid, str(cid)) for cid in channel_ids]
    return ", ".join(titles)


def _channels_prompt(selected: list[int]) -> str:
    if selected:
        return (
            "Выберите каналы (мультивыбор), затем нажмите Готово:\n"
            f"Выбрано: {_format_channel_titles(selected)}"
        )
    return "Выберите каналы (мультивыбор), затем нажмите Готово:"


async def _show_confirmation(target, state: FSMContext) -> None:
    data = await state.get_data()
    op_type = "Доход" if data.get("op_type") == OperationType.INCOME.value else "Расход"
    channels = data.get("channel_ids") or []
    cat_name = data.get("category_name")
    if not cat_name:
        with session_scope() as s:
            cat_row = s.query(Category).filter(Category.id == data.get("category_id")).one_or_none()
            cat_name = cat_row.name if cat_row else data.get("category_code")
    amount_kop = int(data.get("amount_kop") or 0)
    rub = amount_kop // 100
    is_general = data.get("is_general")
    lines = [
        f"Тип: {op_type}",
        f"Каналы: {'общая' if is_general else _format_channel_titles(channels)}",
        f"Категория: {cat_name}",
        f"Сумма: {rub} RUB",
    ]
    if (data.get("category_code") == "custom") and data.get("free_text_reason"):
        lines.append(f"Пояснение: {data.get('free_text_reason')}")
    if data.get("receipt_url"):
        lines.append(f"Чек: {data.get('receipt_url')}")
    if data.get("comment"):
        lines.append(f"Комментарий: {data.get('comment')}")

    await state.set_state(AddOpStates.confirming)
    # target can be Message or CallbackQuery.message
    if hasattr(target, "answer"):
        await target.answer("\n".join(lines), reply_markup=yes_no_kb())
    else:
        await target.edit_text("\n".join(lines), reply_markup=yes_no_kb())


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddOpStates.choosing_type)
    await message.answer("Выберите тип операции:", reply_markup=operation_type_kb())


@router.message(Command("in"))
async def cmd_in(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(op_type=OperationType.INCOME.value)
    with session_scope() as s:
        cats = (
            s.query(Category)
            .filter(Category.is_active.is_(True))
            .order_by(Category.name)
            .all()
        )
        items: list[tuple[int, str, str]] = [
            (c.id, c.name, c.code) for c in cats if c.code in INCOME_CATEGORY_CODES
        ]
    await state.set_state(AddOpStates.choosing_category)
    await message.answer("Выберите категорию дохода:", reply_markup=categories_kb(items))


@router.message(Command("out"))
async def cmd_out(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(op_type=OperationType.EXPENSE.value)
    with session_scope() as s:
        cats = (
            s.query(Category)
            .filter(Category.is_active.is_(True))
            .order_by(Category.name)
            .all()
        )
        items: list[tuple[int, str, str]] = [
            (c.id, c.name, c.code) for c in cats if c.code in EXPENSE_CATEGORY_CODES
        ]
    await state.set_state(AddOpStates.choosing_category)
    await message.answer("Выберите категорию расхода:", reply_markup=categories_kb(items))


@router.callback_query(F.data.startswith("op_type:"), AddOpStates.choosing_type)
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    if action == "income":
        await state.update_data(op_type=OperationType.INCOME.value)
        filter_codes = INCOME_CATEGORY_CODES
        title = "Выберите категорию дохода:"
    else:
        await state.update_data(op_type=OperationType.EXPENSE.value)
        filter_codes = EXPENSE_CATEGORY_CODES
        title = "Выберите категорию расхода:"

    with session_scope() as s:
        cats = (
            s.query(Category)
            .filter(Category.is_active.is_(True))
            .order_by(Category.name)
            .all()
        )
        items: list[tuple[int, str, str]] = [
            (c.id, c.name, c.code) for c in cats if c.code in filter_codes
        ]
    await state.set_state(AddOpStates.choosing_category)
    await callback.message.edit_text(title, reply_markup=categories_kb(items))
    await callback.answer()


@router.callback_query(F.data == "back:type")
async def back_to_type(callback: CallbackQuery, state: FSMContext) -> None:
    logger.info("back_to_type from state=%s", await state.get_state())
    await state.set_state(AddOpStates.choosing_type)
    await callback.message.edit_text("Выберите тип операции:", reply_markup=operation_type_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"), AddOpStates.choosing_category)
async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
    logger.info("choose_category payload=%s state=%s", callback.data, await state.get_state())
    _, id_str = callback.data.split(":", 1)
    if not id_str.isdigit():
        await callback.answer("Некорректная категория")
        return
    cat_id = int(id_str)
    with session_scope() as s:
        cat = s.query(Category).filter(Category.id == cat_id).one_or_none()
        if not cat:
            await callback.answer("Нет такой категории")
            return
        cat_code = cat.code
        await state.update_data(category_id=cat.id, category_code=cat_code, category_name=cat.name)

    if cat_code == "custom":
        await state.set_state(AddOpStates.entering_reason)
        await callback.message.edit_text("Опишите назначение операции (свободный текст):")
    else:
        await state.set_state(AddOpStates.choosing_channels)
        with session_scope() as s:
            q = (
                s.query(Channel)
                .filter(Channel.is_active.is_(True))
                .order_by(Channel.created_at.desc())
                .limit(25)
            )
            ch_items = [(ch.id, ch.title) for ch in q.all()]
        data = await state.get_data()
        selected = list(data.get("channel_ids") or [])
        await callback.message.edit_text(
            _channels_prompt(selected),
            reply_markup=channels_kb(ch_items, selected_ids=selected),
        )
    await callback.answer()


# Fallback: handle category press only when not in the expected state
@router.callback_query(F.data.startswith("cat:"), ~StateFilter(AddOpStates.choosing_category))
async def choose_category_any(callback: CallbackQuery, state: FSMContext) -> None:
    logger.info("choose_category_any payload=%s state=%s", callback.data, await state.get_state())
    await choose_category(callback, state)


@router.callback_query(F.data == "ch_general", AddOpStates.choosing_channels)
async def choose_general(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(is_general=True, channel_ids=[])
    await state.set_state(AddOpStates.entering_amount)
    await callback.message.edit_text("Введите сумму, например: 1200, 1200.50 или 1 200,50:")
    await callback.answer()


@router.callback_query(F.data.startswith("ch:"), AddOpStates.choosing_channels)
async def toggle_channel(callback: CallbackQuery, state: FSMContext) -> None:
    _, id_str = callback.data.split(":", 1)
    if not id_str.isdigit():
        await callback.answer("Некорректный канал")
        return
    ch_id = int(id_str)
    data = await state.get_data()
    selected = list(data.get("channel_ids") or [])
    if ch_id in selected:
        selected.remove(ch_id)
    else:
        selected.append(ch_id)
    await state.update_data(channel_ids=selected, is_general=False)
    with session_scope() as s:
        q = (
            s.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.desc())
            .limit(25)
        )
        ch_items = [(ch.id, ch.title) for ch in q.all()]
    await callback.message.edit_text(
        _channels_prompt(selected),
        reply_markup=channels_kb(ch_items, selected_ids=selected),
    )
    await callback.answer("Готово")


@router.callback_query(F.data == "ch_done", AddOpStates.choosing_channels)
async def channels_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("is_general") and not data.get("channel_ids"):
        await callback.answer("Выберите хотя бы один канал или 'Без канала'", show_alert=True)
        return
    await state.set_state(AddOpStates.entering_amount)
    await callback.message.edit_text("Введите сумму, например: 1200, 1200.50 или 1 200,50:")
    await callback.answer()


@router.message(AddOpStates.entering_reason)
async def enter_reason(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пояснение обязательно. Введите текст:")
        return
    await state.update_data(free_text_reason=text)
    await state.set_state(AddOpStates.choosing_channels)
    with session_scope() as s:
        q = (
            s.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.desc())
            .limit(25)
        )
        ch_items = [(ch.id, ch.title) for ch in q.all()]
    await message.answer(
        "Выберите каналы (мультивыбор), затем нажмите Готово:",
        reply_markup=channels_kb(ch_items),
    )


@router.message(AddOpStates.entering_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    try:
        amount_kop = parse_amount_rub_to_kop(message.text or "")
    except AmountParseError as e:
        await message.answer(str(e))
        return
    await state.update_data(amount_kop=amount_kop)
    await state.set_state(AddOpStates.entering_receipt)
    await message.answer(
        "Добавьте ссылку на чек (URL) или нажмите Пропустить:",
        reply_markup=skip_kb("skip:receipt"),
    )


@router.callback_query(F.data == "skip:receipt", AddOpStates.entering_receipt)
async def skip_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(receipt_url=None)
    await state.set_state(AddOpStates.entering_comment)
    await callback.message.edit_text(
        "Добавьте комментарий или нажмите Пропустить:", reply_markup=skip_kb("skip:comment")
    )
    await callback.answer()


@router.message(AddOpStates.entering_receipt)
async def enter_receipt(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    await state.update_data(receipt_url=url or None)
    await state.set_state(AddOpStates.entering_comment)
    await message.answer(
        "Добавьте комментарий или нажмите Пропустить:", reply_markup=skip_kb("skip:comment")
    )


@router.callback_query(F.data == "skip:comment", AddOpStates.entering_comment)
async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(comment=None)
    await _show_confirmation(callback.message, state)
    await callback.answer()


@router.message(AddOpStates.entering_comment)
async def enter_comment(message: Message, state: FSMContext) -> None:
    comment = (message.text or "").strip()
    await state.update_data(comment=comment or None)
    await _show_confirmation(message, state)


@router.callback_query(F.data == "cancel", AddOpStates.confirming)
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Операция отменена.")
    await callback.answer()


@router.callback_query(F.data == "confirm", AddOpStates.confirming)
async def confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    if not user:
        await callback.answer("Техническая ошибка")
        return
    data = await state.get_data()
    with session_scope() as s:
        cat = s.query(Category).filter(Category.id == data["category_id"]).one()
        db_user = s.query(User).filter(User.tg_user_id == user.id).one()
        created_at = now_msk()
        dedup = build_dedup_hash(
            tg_user_id=user.id,
            op_type=int(data["op_type"]),
            category_code=cat.code,
            amount_kop=int(data["amount_kop"]),
            channel_ids=[int(cid) for cid in (data.get("channel_ids") or [])],
            is_general=bool(data.get("is_general")),
            created_at=created_at,
        )
        op = Operation(
            created_at=created_at,
            op_type=int(data["op_type"]),
            category_id=cat.id,
            amount_kop=int(data["amount_kop"]),
            currency="RUB",
            free_text_reason=(data.get("free_text_reason") or None),
            receipt_url=(data.get("receipt_url") or None),
            comment=(data.get("comment") or None),
            created_by_user_id=db_user.id,
            is_general=bool(data.get("is_general")),
            dedup_hash=dedup,
        )
        try:
            s.add(op)
            s.flush()
            for ch_id in (data.get("channel_ids") or []):
                s.execute(OperationChannel.insert().values(operation_id=op.id, channel_id=int(ch_id)))
            s.flush()
        except IntegrityError:
            s.rollback()
            existing = s.query(Operation).filter(Operation.dedup_hash == dedup).one_or_none()
            if existing:
                res = s.execute(
                    OperationChannel.select().where(OperationChannel.c.operation_id == existing.id)
                )
                channels_count = len(list(res))
                op_type_txt = "Доход" if existing.op_type == OperationType.INCOME.value else "Расход"
                rub = existing.amount_kop // 100
                await callback.message.edit_text(
                    f"Дубликат: уже есть операция #{existing.id}\n"
                    f"Тип: {op_type_txt}\nКатегория: {cat.name}\n"
                    f"Сумма: {rub} RUB\nОбщая: {'да' if existing.is_general else 'нет'}\n"
                    f"Каналов: {channels_count}"
                )
            else:
                await callback.message.edit_text("Похоже, такая операция уже была сохранена (дубликат).")
            await state.clear()
            await callback.answer()
            return

    await state.clear()
    await callback.message.edit_text("Операция сохранена.")
    await callback.answer()
