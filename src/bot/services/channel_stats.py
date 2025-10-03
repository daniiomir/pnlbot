from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from telethon.tl.types import Message
from telethon.errors.rpcerrorlist import ChannelPrivateError

from bot.db.base import session_scope
from bot.db.models import Channel, ChannelDailySnapshot, PostSnapshot, ChannelSubscribersHistory
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
    logger.info(
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
        logger.info("Collect channel=%s subs=%s", tg_chat_id, subs)

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
    logger.info("Collect (single) channel=%s subs=%s", tg_chat_id, subs)

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

    return {
        "channels": 1,
        "daily_inserted": daily_inserted,
        "daily_updated": daily_updated,
        "posts_inserted": posts_inserted,
        "posts_updated": posts_updated,
    }


