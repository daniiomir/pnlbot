from datetime import datetime
from zoneinfo import ZoneInfo

from bot.services.dedup import build_dedup_hash


def test_dedup_stable_order():
    dt = datetime(2024, 1, 1, 12, 34, 56, tzinfo=ZoneInfo("Europe/Moscow"))
    h1 = build_dedup_hash(1, 1, "ad_revenue", 100, [5, 2, 3], False, dt)
    h2 = build_dedup_hash(1, 1, "ad_revenue", 100, [3, 5, 2], False, dt)
    assert h1 == h2
