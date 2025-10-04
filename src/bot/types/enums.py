from __future__ import annotations

from enum import IntEnum


class OperationType(IntEnum):
    INCOME = 1
    EXPENSE = 2


DEFAULT_CATEGORY_SEED = [
    ("ad_revenue", "Выручка с прямой рекламы"),
    ("ad_revenue_rsy", "Выручка с РСЯ"),
    ("ad_revenue_bk", "Выручка с БК"),
    ("admins_pay", "Оплата работы админов"),
    ("ad_purchase", "Закупка рекламы"),
    ("personal_invest", "Личные вложения"),
    ("services_costs", "Затраты на сервисы"),
    ("it_infra_costs", "Затраты на IT инфру"),
    ("custom", "Ручной ввод"),
]

# Category groups used for UI filtering
INCOME_CATEGORY_CODES = {"ad_revenue", "ad_revenue_rsy", "ad_revenue_bk", "custom"}
EXPENSE_CATEGORY_CODES = {"admins_pay", "ad_purchase", "personal_invest", "services_costs", "it_infra_costs", "custom"}


__all__ = [
    "OperationType",
    "DEFAULT_CATEGORY_SEED",
    "INCOME_CATEGORY_CODES",
    "EXPENSE_CATEGORY_CODES",
]
