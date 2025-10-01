from __future__ import annotations

import re

MAX_INT64 = 2**63 - 1


class AmountParseError(ValueError):
    pass


def parse_amount_rub_to_kop(text: str) -> int:
    if text is None:
        raise AmountParseError(
            "Введите сумму, например: 1200, 1 200,50 или 1200.50"
        )
    raw = text.strip()
    if not raw:
        raise AmountParseError(
            "Введите сумму, например: 1200, 1 200,50 или 1200.50"
        )
    # Remove spaces used as thousands separators
    s = raw.replace(" ", "")
    # Use dot as decimal separator; allow comma as decimal too
    s = s.replace(",", ".")
    # Validate format: digits with optional . and 1-2 decimals
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        raise AmountParseError(
            "Некорректный формат. Примеры: 1200, 1 200,50, 1200.50"
        )
    if "." in s:
        rub_str, kop_str = s.split(".", 1)
        rub = int(rub_str)
        # Normalize 1 decimal place to kopeks
        if len(kop_str) == 1:
            kop = int(kop_str) * 10
        else:
            kop = int(kop_str[:2])
    else:
        rub = int(s)
        kop = 0
    if rub < 0:
        raise AmountParseError("Отрицательные значения недопустимы")
    amount_kop = rub * 100 + kop
    if amount_kop > MAX_INT64:
        raise AmountParseError("Слишком большая сумма")
    return amount_kop


__all__ = ["parse_amount_rub_to_kop", "AmountParseError"]
