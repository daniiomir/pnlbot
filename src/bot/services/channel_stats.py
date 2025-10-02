from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable

from telethon.tl.types import Message
from telethon.errors.rpcerrorlist import ChannelPrivateError

from bot.db.base import session_scope
from bot.db.models import Channel, ChannelDailySnapshot, PostSnapshot
from bot.services.mtproto_client import get_telethon
from bot.services.time import MSK_TZ, now_msk

logger = logging.getLogger(__name__)


async def fetch_channel_subscribers_count(tg_chat_id: int) -> int | None:
    client = get_telethon()
    try:
        entity = await client.get_entity(tg_chat_id)
        full = await client.get_entity(entity)
        # Telethon does not expose participants_count on entity directly; use GetFullChannel via client(functions)
        from telethon.tl.functions.channels import GetFullChannelRequest

        full_info = await client(GetFullChannelRequest(channel=entity))
        count = getattr(getattr(full_info, 'full_chat', None), 'participants_count', None)
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
        # Telethon's iter_messages supports date range via offset_date and min_date
        # We'll iterate until messages go earlier than start_dt
        async for msg in client.iter_messages(entity, offset_date=end_dt, reverse=True):
            if msg.date is None:
                continue
            # Telethon msg.date is UTC
            if msg.date < start_dt.astimezone(msg.date.tzinfo):
                break
            if msg.date <= end_dt and msg.date >= start_dt:
                yield msg
    except ChannelPrivateError:
        logger.warning("Channel is private or inaccessible: %s", tg_chat_id)
    except Exception:
        logger.exception("Failed to iterate posts for %s", tg_chat_id)


async def collect_daily_for_all_channels(snapshot_date_local: datetime) -> None:
    start_local = snapshot_date_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1) - timedelta(microseconds=1)
    # Convert MSK to UTC for Telethon comparisons (Telethon Message.date is UTC)
    start_utc = start_local.astimezone(MSK_TZ).astimezone(tz=None)
    end_utc = end_local.astimezone(MSK_TZ).astimezone(tz=None)

    with session_scope() as s:
        channels = s.query(Channel).filter(Channel.is_active == True).all()  # noqa: E712

    for ch in channels:
        subs = await fetch_channel_subscribers_count(ch.tg_chat_id)
        collected_at = now_msk()

        # Upsert channel_daily_snapshots
        with session_scope() as s:
            existing = (
                s.query(ChannelDailySnapshot)
                .filter(
                    ChannelDailySnapshot.channel_id == ch.id,
                    ChannelDailySnapshot.snapshot_date == start_local.date(),
                )
                .one_or_none()
            )
            if existing:
                existing.subscribers_count = subs
                existing.collected_at = collected_at
            else:
                s.add(
                    ChannelDailySnapshot(
                        channel_id=ch.id,
                        snapshot_date=start_local.date(),
                        subscribers_count=subs,
                        collected_at=collected_at,
                    )
                )

        # Posts
        async for msg in iter_channel_posts_in_range(ch.tg_chat_id, start_utc, end_utc):
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
                        PostSnapshot.channel_id == ch.id,
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
                else:
                    s.add(
                        PostSnapshot(
                            channel_id=ch.id,
                            message_id=msg.id,
                            posted_at=msg.date,
                            snapshot_date=start_local.date(),
                            views=views,
                            forwards=forwards,
                            reactions_total=reactions_total,
                            collected_at=collected_at,
                        )
                    )


