from __future__ import annotations

import hashlib
from typing import Iterable
from datetime import datetime

from .time import floor_to_3_minutes


def build_dedup_hash(
    tg_user_id: int,
    op_type: int,
    category_code: str,
    amount_kop: int,
    channel_ids: Iterable[int],
    is_general: bool,
    created_at: datetime,
) -> str:
    minute_dt = floor_to_3_minutes(created_at)
    minute_str = minute_dt.isoformat()
    channels_sorted = ",".join(str(cid) for cid in sorted(set(channel_ids)))
    payload = "|".join(
        [
            str(tg_user_id),
            str(op_type),
            category_code,
            str(amount_kop),
            channels_sorted,
            "1" if is_general else "0",
            minute_str,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["build_dedup_hash"]
