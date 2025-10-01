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

# Category groups used for UI filtering
INCOME_CATEGORY_CODES = {"ad_revenue", "custom"}
EXPENSE_CATEGORY_CODES = {"admins_pay", "ad_purchase", "personal_invest", "custom"}


__all__ = [
    "OperationType",
    "DEFAULT_CATEGORY_SEED",
    "INCOME_CATEGORY_CODES",
    "EXPENSE_CATEGORY_CODES",
]
