from __future__ import annotations

MAX_INT64 = 2**63 - 1


class AmountParseError(ValueError):
    pass


def parse_amount_rub_to_kop(text: str) -> int:
    if text is None:
        raise AmountParseError("Введите сумму целым числом в рублях, например: 1200")
    s = text.strip().replace(" ", "")
    if not s or not s.isdigit():
        raise AmountParseError("Сумма должна быть целым числом без знака, например: 1 200")
    rub = int(s)
    if rub < 0:
        raise AmountParseError("Отрицательные значения недопустимы")
    amount_kop = rub * 100
    if amount_kop > MAX_INT64:
        raise AmountParseError("Слишком большая сумма")
    return amount_kop


__all__ = ["parse_amount_rub_to_kop", "AmountParseError"]
