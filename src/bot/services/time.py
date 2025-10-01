from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MSK_TZ = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(tz=MSK_TZ)


def floor_to_minute(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MSK_TZ)
    return dt.replace(second=0, microsecond=0)


__all__ = ["MSK_TZ", "now_msk", "floor_to_minute"]
