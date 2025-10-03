from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta, timezone, date
from typing import Iterable, Any, Sequence

from telethon.tl.types import Message
from telethon.tl.functions.stats import GetBroadcastStatsRequest, LoadAsyncGraphRequest
from telethon.tl.types import StatsGraph, StatsGraphAsync
from telethon.errors.rpcerrorlist import ChannelPrivateError

from bot.db.base import session_scope
from bot.db.models import (
    Channel,
    ChannelDailySnapshot,
    PostSnapshot,
    ChannelSubscribersHistory,
    ChannelDailyChurn,
)
from bot.services.mtproto_client import get_telethon
from bot.services.time import MSK_TZ, now_msk

logger = logging.getLogger()


async def fetch_channel_subscribers_count(tg_chat_id: int) -> int | None:
    client = get_telethon()
    try:
        entity = await client.get_entity(tg_chat_id)
        full = await client.get_entity(entity)
        # Telethon does not expose participants_count on entity directly; use GetFullChannel via client(functions)
        from telethon.tl.functions.channels import GetFullChannelRequest

        full_info = await client(GetFullChannelRequest(channel=entity))
        count = getattr(getattr(full_info, 'full_chat', None), 'participants_count', None)
        if count is None:
            # Fallback: use get_participants with limit=0 to retrieve total count
            try:
                participants = await client.get_participants(entity, limit=0)
                count = getattr(participants, 'total', None)
            except Exception:
                count = None
        return int(count) if count is not None else None
    except ChannelPrivateError:
        logger.warning("Channel is private or inaccessible: %s", tg_chat_id)
        return None
    except Exception:
        logger.exception("Failed to fetch subscribers count for %s", tg_chat_id)
        return None


async def iter_channel_posts_in_range(tg_chat_id: int, start_dt: datetime, end_dt: datetime) -> Iterable[Message]:
    client = get_telethon()
    try:
        entity = await client.get_entity(tg_chat_id)
        # Iterate from most recent backwards until we exit the window
        async for msg in client.iter_messages(entity, offset_date=end_dt, reverse=False):
            if msg.date is None:
                continue
            # Telethon msg.date is UTC
            if msg.date < start_dt:
                break
            if msg.date <= end_dt and msg.date >= start_dt:
                yield msg
    except ChannelPrivateError:
        logger.warning("Channel is private or inaccessible: %s", tg_chat_id)
    except Exception:
        logger.exception("Failed to iterate posts for %s", tg_chat_id)


async def collect_daily_for_all_channels(snapshot_date_local: datetime) -> dict[str, int]:
    start_local = snapshot_date_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # For daily subscribers snapshot we use today's local date (MSK)
    # For posts, collect last 72 hours relative to now
    now_utc = now_msk().astimezone(timezone.utc)
    posts_start_utc = now_utc - timedelta(hours=72)
    posts_end_utc = now_utc

    # Fetch only primitive fields to avoid DetachedInstanceError after session closes
    with session_scope() as s:
        rows = (
            s.query(Channel.id, Channel.tg_chat_id)
            .filter(Channel.is_active == True)  # noqa: E712
            .all()
        )
        channels = [(row.id, row.tg_chat_id) for row in rows]
    logger.debug(
        "Collecting stats for %s: active_channels=%s",
        start_local.date(),
        len(channels),
    )

    channels_processed = 0
    daily_inserted = 0
    daily_updated = 0
    posts_inserted = 0
    posts_updated = 0

    for ch_id, tg_chat_id in channels:
        subs = await fetch_channel_subscribers_count(tg_chat_id)
        collected_at = now_msk()
        logger.debug("Collect channel=%s subs=%s", tg_chat_id, subs)

        # Upsert channel_daily_snapshots
        with session_scope() as s:
            existing = (
                s.query(ChannelDailySnapshot)
                .filter(
                    ChannelDailySnapshot.channel_id == ch_id,
                    ChannelDailySnapshot.snapshot_date == start_local.date(),
                )
                .one_or_none()
            )
            if existing:
                existing.subscribers_count = subs
                existing.collected_at = collected_at
                daily_updated += 1
            else:
                s.add(
                    ChannelDailySnapshot(
                        channel_id=ch_id,
                        snapshot_date=start_local.date(),
                        subscribers_count=subs,
                        collected_at=collected_at,
                    )
                )
                daily_inserted += 1

            # History row for churn analysis
            s.add(
                ChannelSubscribersHistory(
                    channel_id=ch_id,
                    collected_at=collected_at,
                    subscribers_count=subs,
                )
            )

        # Update channel health markers
        with session_scope() as s:
            ch = s.query(Channel).filter(Channel.id == ch_id).one_or_none()
            if ch is not None:
                if subs is not None:
                    ch.last_success_at = collected_at
                    ch.last_error = None
                else:
                    ch.last_error = "failed to fetch subscribers"

        # Posts
        async for msg in iter_channel_posts_in_range(tg_chat_id, posts_start_utc, posts_end_utc):
            views = getattr(msg, 'views', None)
            forwards = getattr(msg, 'forwards', None)
            reactions_total = None
            try:
                if getattr(msg, 'reactions', None) and getattr(msg.reactions, 'results', None):
                    reactions_total = sum(getattr(r, 'count', 0) for r in msg.reactions.results)
            except Exception:
                reactions_total = None

            with session_scope() as s:
                existing = (
                    s.query(PostSnapshot)
                    .filter(
                        PostSnapshot.channel_id == ch_id,
                        PostSnapshot.message_id == msg.id,
                        PostSnapshot.snapshot_date == start_local.date(),
                    )
                    .one_or_none()
                )
                if existing:
                    existing.views = views
                    existing.forwards = forwards
                    existing.reactions_total = reactions_total
                    existing.collected_at = collected_at
                    posts_updated += 1
                else:
                    s.add(
                        PostSnapshot(
                            channel_id=ch_id,
                            message_id=msg.id,
                            posted_at=msg.date,
                            snapshot_date=start_local.date(),
                            views=views,
                            forwards=forwards,
                            reactions_total=reactions_total,
                            collected_at=collected_at,
                        )
                    )
                    posts_inserted += 1

        # Churn history (requires admin rights): stats.getBroadcastStats growth_graph
        try:
            await _collect_and_store_churn_history(ch_id, tg_chat_id, collected_at)
        except Exception:
            logger.exception(
                "Churn collection failed for %s (check admin rights / limits)", tg_chat_id
            )

        channels_processed += 1

    logger.info(
        "Collected: channels=%s daily(ins=%s,upd=%s) posts(ins=%s,upd=%s)",
        channels_processed,
        daily_inserted,
        daily_updated,
        posts_inserted,
        posts_updated,
    )

    return {
        "channels": channels_processed,
        "daily_inserted": daily_inserted,
        "daily_updated": daily_updated,
        "posts_inserted": posts_inserted,
        "posts_updated": posts_updated,
    }


async def collect_for_channel(channel_id: int, tg_chat_id: int, when_local: datetime) -> dict[str, int]:
    """Collect subscribers (by local day) and posts (last 72h) for a single channel.

    Returns counters similar to collect_daily_for_all_channels but scoped to one channel.
    """
    start_local = when_local.replace(hour=0, minute=0, second=0, microsecond=0)
    now_utc = now_msk().astimezone(timezone.utc)
    posts_start_utc = now_utc - timedelta(hours=72)
    posts_end_utc = now_utc

    subs = await fetch_channel_subscribers_count(tg_chat_id)
    collected_at = now_msk()
    logger.debug("Collect (single) channel=%s subs=%s", tg_chat_id, subs)

    daily_inserted = 0
    daily_updated = 0
    posts_inserted = 0
    posts_updated = 0

    # Upsert daily subscribers snapshot
    with session_scope() as s:
        existing = (
            s.query(ChannelDailySnapshot)
            .filter(
                ChannelDailySnapshot.channel_id == channel_id,
                ChannelDailySnapshot.snapshot_date == start_local.date(),
            )
            .one_or_none()
        )
        if existing:
            existing.subscribers_count = subs
            existing.collected_at = collected_at
            daily_updated += 1
        else:
            s.add(
                ChannelDailySnapshot(
                    channel_id=channel_id,
                    snapshot_date=start_local.date(),
                    subscribers_count=subs,
                    collected_at=collected_at,
                )
            )
            daily_inserted += 1

        # History row for churn analysis
        s.add(
            ChannelSubscribersHistory(
                channel_id=channel_id,
                collected_at=collected_at,
                subscribers_count=subs,
            )
        )

    # Update channel health
    with session_scope() as s:
        ch = s.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if ch is not None:
            if subs is not None:
                ch.last_success_at = collected_at
                ch.last_error = None
            else:
                ch.last_error = "failed to fetch subscribers"

    # Posts snapshots
    async for msg in iter_channel_posts_in_range(tg_chat_id, posts_start_utc, posts_end_utc):
        views = getattr(msg, 'views', None)
        forwards = getattr(msg, 'forwards', None)
        reactions_total = None
        try:
            if getattr(msg, 'reactions', None) and getattr(msg.reactions, 'results', None):
                reactions_total = sum(getattr(r, 'count', 0) for r in msg.reactions.results)
        except Exception:
            reactions_total = None

        with session_scope() as s:
            existing = (
                s.query(PostSnapshot)
                .filter(
                    PostSnapshot.channel_id == channel_id,
                    PostSnapshot.message_id == msg.id,
                    PostSnapshot.snapshot_date == start_local.date(),
                )
                .one_or_none()
            )
            if existing:
                existing.views = views
                existing.forwards = forwards
                existing.reactions_total = reactions_total
                existing.collected_at = collected_at
                posts_updated += 1
            else:
                s.add(
                    PostSnapshot(
                        channel_id=channel_id,
                        message_id=msg.id,
                        posted_at=msg.date,
                        snapshot_date=start_local.date(),
                        views=views,
                        forwards=forwards,
                        reactions_total=reactions_total,
                        collected_at=collected_at,
                    )
                )
                posts_inserted += 1

    # Churn (requires admin rights)
    try:
        await _collect_and_store_churn_history(channel_id, tg_chat_id, collected_at)
    except Exception:
        logger.exception(
            "Churn collection failed for %s (check admin rights / limits)", tg_chat_id
        )

    return {
        "channels": 1,
        "daily_inserted": daily_inserted,
        "daily_updated": daily_updated,
        "posts_inserted": posts_inserted,
        "posts_updated": posts_updated,
    }


async def _collect_and_store_churn_history(channel_id: int, tg_chat_id: int, collected_at: datetime) -> None:
    """Fetch followers graph (Joined/Left) and upsert daily churn."""
    client = get_telethon()
    entity = await client.get_entity(tg_chat_id)
    stats = await client(GetBroadcastStatsRequest(channel=entity, dark=False))

    followers_graph = getattr(stats, "followers_graph", None)
    if followers_graph is None:
        logger.debug("Churn: followers graph is missing for tg_chat_id=%s", tg_chat_id)
        return

    graph = followers_graph
    if isinstance(graph, StatsGraphAsync):
        try:
            graph = await client(LoadAsyncGraphRequest(token=graph.token))
        except Exception:
            logger.exception("Churn: failed to load async followers graph for %s", tg_chat_id)
            return

    if not isinstance(graph, StatsGraph):
        logger.debug("Churn: unsupported followers graph type for tg_chat_id=%s: %s", tg_chat_id, type(graph).__name__)
        return

    data_obj = getattr(graph, "json", None)
    raw_json: str | None = getattr(data_obj, "data", None) if data_obj is not None else None
    if not raw_json:
        logger.debug("Churn: empty followers graph JSON for tg_chat_id=%s", tg_chat_id)
        return

    try:
        parsed = json.loads(raw_json)
    except Exception:
        logger.exception("Churn: failed to parse followers graph JSON for %s", tg_chat_id)
        return

    if not isinstance(parsed, dict) or not isinstance(parsed.get("columns"), list):
        logger.debug("Churn: unsupported followers graph JSON structure (no columns) for tg_chat_id=%s", tg_chat_id)
        return

    cols = parsed.get("columns")
    names = parsed.get("names") or {}

    # Extract x, joined, left series
    x_values: list[int] = []
    joined_values: list[int | None] | None = None
    left_values: list[int | None] | None = None

    for col in cols:
        if not isinstance(col, list) or not col:
            continue
        key = col[0]
        values = col[1:]
        if key == "x":
            x_values = values

    # Prefer mapping via names where available, else fallback to y0/y1
    title_to_key: dict[str, str] = {}
    try:
        for k, title in (names or {}).items():
            if isinstance(title, str):
                title_to_key[title.strip().lower()] = k
    except Exception:
        title_to_key = {}

    joined_key = title_to_key.get("joined") or title_to_key.get("joins") or "y0"
    left_key = title_to_key.get("left") or title_to_key.get("leaves") or "y1"

    for col in cols:
        if not isinstance(col, list) or not col:
            continue
        key = col[0]
        values = col[1:]
        if key == joined_key:
            joined_values = [int(v) if v is not None else None for v in values]
        elif key == left_key:
            left_values = [int(v) if v is not None else None for v in values]

    if not x_values or (joined_values is None and left_values is None):
        logger.debug("Churn: followers graph missing series for tg_chat_id=%s", tg_chat_id)
        return

    # Normalize timestamps (ms or s) to UTC dates
    dates: list[date] = []
    for ts in x_values:
        try:
            tsn = ts
            if isinstance(tsn, (int, float)) and tsn > 10_000_000_000:
                tsn = int(tsn // 1000)
            dates.append(datetime.fromtimestamp(int(tsn), tz=timezone.utc).date())
        except Exception:
            dates.append(None)  # type: ignore[arg-type]

    # Keep a longer retention to support horizons (e.g., 72h vs 48h)
    valid: list[tuple[int, date]] = [(idx, d) for idx, d in enumerate(dates) if d is not None]
    if not valid:
        logger.debug("Churn: no valid dates in followers graph for tg_chat_id=%s", tg_chat_id)
        return
    # For safety, use the last index per date in case of duplicates
    last_index_by_date: dict[date, int] = {}
    for idx, d in valid:
        last_index_by_date[d] = idx
    sorted_unique_dates = sorted(last_index_by_date.keys())
    selected_dates = sorted_unique_dates[-7:]

    with session_scope() as s:
        rows_written = 0
        for d_local in selected_dates:
            idx = last_index_by_date[d_local]
            joins_val = joined_values[idx] if joined_values and idx < len(joined_values) else None
            leaves_val = left_values[idx] if left_values and idx < len(left_values) else None

            existing = (
                s.query(ChannelDailyChurn)
                .filter(
                    ChannelDailyChurn.channel_id == channel_id,
                    ChannelDailyChurn.snapshot_date == d_local,
                )
                .one_or_none()
            )
            if existing:
                existing.joins_count = joins_val
                existing.leaves_count = leaves_val
                existing.collected_at = collected_at
            else:
                s.add(
                    ChannelDailyChurn(
                        channel_id=channel_id,
                        snapshot_date=d_local,
                        joins_count=joins_val,
                        leaves_count=leaves_val,
                        collected_at=collected_at,
                    )
                )
            rows_written += 1

    try:
        logger.debug(
            "Churn: upserted %s rows (dates=%s) from followers_graph for tg_chat_id=%s",
            rows_written,
            ", ".join(str(d) for d in selected_dates),
            tg_chat_id,
        )
    except Exception:
        logger.debug("Churn: upserted %s rows from followers_graph for tg_chat_id=%s", rows_written, tg_chat_id)


