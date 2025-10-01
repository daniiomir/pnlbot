from __future__ import annotations

from enum import IntEnum


class OperationType(IntEnum):
    INCOME = 1
    EXPENSE = 2


DEFAULT_CATEGORY_SEED = [
    ("ad_revenue", "Доход с рекламы"),
    ("admins_pay", "Оплата работы админов"),
    ("ad_purchase", "Закупка рекламы"),
    ("personal_invest", "Личные вложения"),
    ("custom", "Ручной ввод"),
]


__all__ = ["OperationType", "DEFAULT_CATEGORY_SEED"]
