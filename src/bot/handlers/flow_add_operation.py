from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.exc import IntegrityError

from bot.keyboards.common import operation_type_kb, yes_no_kb
from bot.types.enums import OperationType
from bot.services.parsing import parse_amount_rub_to_kop, AmountParseError
from bot.services.time import now_msk
from bot.services.dedup import build_dedup_hash
from bot.db.base import session_scope
from bot.db.models import Category, Channel, Operation, OperationChannel, User

logger = logging.getLogger(__name__)

router = Router()


class AddOpStates(StatesGroup):
    choosing_type = State()
    choosing_channels = State()
    choosing_category = State()
    entering_reason = State()
    entering_amount = State()
    confirming = State()


@dataclass
class AddOpData:
    op_type: int | None = None
    is_general: bool = False
    channel_ids: List[int] | None = None
    category_id: int | None = None
    category_code: str | None = None
    free_text_reason: str | None = None
    amount_kop: int | None = None


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddOpStates.choosing_type)
    await message.answer("Выберите тип операции:", reply_markup=operation_type_kb())


@router.callback_query(F.data.startswith("op_type:"), AddOpStates.choosing_type)
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    if action == "income":
        await state.update_data(op_type=OperationType.INCOME.value)
    else:
        await state.update_data(op_type=OperationType.EXPENSE.value)
    await state.set_state(AddOpStates.choosing_channels)
    await callback.message.edit_text(
        "Укажите каналы (введите chat_id через пробел) или напишите 0 для общей операции"
    )
    await callback.answer()


@router.message(AddOpStates.choosing_channels)
async def input_channels(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    text = text.strip()
    is_general = text == "0"
    channel_ids: List[int] = []
    if not is_general:
        for part in text.split():
            if not part.isdigit():
                await message.answer("ID каналов должны быть числами. Введите ещё раз или 0.")
                return
            channel_ids.append(int(part))

    # Validate channels exist or create
    with session_scope() as s:
        existing_map: dict[int, int] = {}
        if channel_ids:
            q = s.query(Channel).filter(Channel.tg_chat_id.in_(channel_ids))
            for ch in q.all():
                existing_map[ch.tg_chat_id] = ch.id
        for cid in channel_ids:
            if cid not in existing_map:
                ch = Channel(tg_chat_id=cid, title=None, username=None, created_at=now_msk())
                s.add(ch)
                s.flush()
                existing_map[cid] = ch.id
        selected_channel_db_ids = [existing_map[cid] for cid in channel_ids]

    await state.update_data(is_general=is_general, channel_ids=selected_channel_db_ids)
    await state.set_state(AddOpStates.choosing_category)

    # Show categories
    with session_scope() as s:
        cats = s.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
        lines = [f"{c.id}. {c.name} ({c.code})" for c in cats]
    await message.answer(
        "Выберите категорию, отправив её номер:\n" + "\n".join(lines)
    )


@router.message(AddOpStates.choosing_category)
async def choose_category(message: Message, state: FSMContext) -> None:
    if not (message.text and message.text.isdigit()):
        await message.answer("Введите номер категории из списка.")
        return
    cat_id = int(message.text)
    with session_scope() as s:
        cat = s.query(Category).filter(Category.id == cat_id).one_or_none()
        if not cat:
            await message.answer("Нет такой категории. Повторите ввод.")
            return
        await state.update_data(category_id=cat.id, category_code=cat.code)
    if cat.code == "custom":
        await state.set_state(AddOpStates.entering_reason)
        await message.answer("Опишите назначение операции (свободный текст):")
    else:
        await state.set_state(AddOpStates.entering_amount)
        await message.answer("Введите сумму в рублях (целое число):")


@router.message(AddOpStates.entering_reason)
async def enter_reason(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пояснение обязательно. Введите текст:")
        return
    await state.update_data(free_text_reason=text)
    await state.set_state(AddOpStates.entering_amount)
    await message.answer("Введите сумму в рублях (целое число):")


@router.message(AddOpStates.entering_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    try:
        amount_kop = parse_amount_rub_to_kop(message.text or "")
    except AmountParseError as e:
        await message.answer(str(e))
        return
    await state.update_data(amount_kop=amount_kop)
    data = await state.get_data()
    op_type = "Доход" if data.get("op_type") == OperationType.INCOME.value else "Расход"
    channels = data.get("channel_ids") or []
    cat_code = data.get("category_code")
    rub = amount_kop // 100
    is_general = data.get("is_general")
    lines = [
        f"Тип: {op_type}",
        f"Каналы: {'общая' if is_general else (', '.join(map(str, channels)) or '—')}",
        f"Категория: {cat_code}",
        f"Сумма: {rub} RUB",
    ]
    if cat_code == "custom":
        lines.append(f"Пояснение: {data.get('free_text_reason')}")
    await state.set_state(AddOpStates.confirming)
    await message.answer("\n".join(lines), reply_markup=yes_no_kb())


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
            free_text_reason=data.get("free_text_reason"),
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
                # get channels count
                res = s.execute(
                    OperationChannel.select().where(OperationChannel.c.operation_id == existing.id)
                )
                channels_count = len(list(res))
                op_type_txt = "Доход" if existing.op_type == OperationType.INCOME.value else "Расход"
                rub = existing.amount_kop // 100
                await callback.message.edit_text(
                    f"Дубликат: уже есть операция #{existing.id}\n"
                    f"Тип: {op_type_txt}\nКатегория: {cat.code}\n"
                    f"Сумма: {rub} RUB\nОбщая: {"да" if existing.is_general else "нет"}\n"
                    f"Каналов: {channels_count}"
                )
            else:
                await callback.message.edit_text("Похоже, такая операция уже была сохранена (дубликат).")
            await state.clear()
            await callback.answer()
            return

        op_id = op.id

    await state.clear()
    await callback.message.edit_text(f"Операция сохранена. Номер: {op_id}")
    await callback.answer()
