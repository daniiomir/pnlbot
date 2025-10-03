from __future__ import annotations

import logging

from aiogram import Bot
from datetime import timezone, timedelta

from bot.db.base import session_scope
from bot.db.models import User, Channel, ChannelDailySnapshot, PostSnapshot, ChannelDailyChurn
from sqlalchemy import func
from bot.services.time import now_msk

logger = logging.getLogger()


async def notify_admins(bot: Bot, user_ids: list[int], text: str) -> None:
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
        except Exception:
            logger.exception("Failed to send alert to %s", uid)


async def build_stats_report_text() -> str:
    today = now_msk().date()
    now_moment = now_msk()
    now_utc = now_moment.astimezone(timezone.utc)
    horizons = [24, 48, 72]

    with session_scope() as s:
        channels = (
            s.query(Channel)
            .filter(Channel.is_active.is_(True))
            .order_by(Channel.created_at.desc())
            .all()
        )
        if not channels:
            return "Активных каналов не найдено."

        lines: list[str] = []
        total_subs: int = 0
        total_views_by_h: dict[int, int] = {h: 0 for h in horizons}
        total_joins_by_h: dict[int, int] = {h: 0 for h in horizons}
        total_leaves_by_h: dict[int, int] = {h: 0 for h in horizons}

        for ch in channels:
            title = ch.title or ch.username or str(ch.tg_chat_id)
            daily = (
                s.query(ChannelDailySnapshot)
                .filter(
                    ChannelDailySnapshot.channel_id == ch.id,
                    ChannelDailySnapshot.snapshot_date == today,
                )
                .one_or_none()
            )
            subs = daily.subscribers_count if daily else None
            if subs is not None:
                try:
                    total_subs += int(subs)
                except Exception:
                    pass
            parts: list[str] = [f"<b>{title}</b>", f"👥 {subs if subs is not None else '-'}"]
            for h in horizons:
                start_utc = now_utc - timedelta(hours=h)
                days_window = int((h + 23) // 24)
                start_local_date = (now_moment - timedelta(days=days_window-1)).date()
                cnt, avg_views = (
                    s.query(
                        func.count(PostSnapshot.id),
                        func.avg(PostSnapshot.views),
                    )
                    .filter(
                        PostSnapshot.channel_id == ch.id,
                        PostSnapshot.snapshot_date == today,
                        PostSnapshot.posted_at >= start_utc,
                        PostSnapshot.posted_at <= now_utc,
                    )
                    .one()
                )
                cnt_int = int(cnt or 0)
                avg_int = int((avg_views or 0))
                try:
                    total_views_by_h[h] += avg_int
                except Exception:
                    pass
                er_txt = "-"
                if subs and subs > 0 and avg_views is not None:
                    er = (float(avg_views) / float(subs)) * 100.0
                    er_txt = f"{er:.1f}%"
                joins_sum, leaves_sum = (
                    s.query(
                        func.coalesce(func.sum(ChannelDailyChurn.joins_count), 0),
                        func.coalesce(func.sum(ChannelDailyChurn.leaves_count), 0),
                    )
                    .filter(
                        ChannelDailyChurn.channel_id == ch.id,
                        ChannelDailyChurn.snapshot_date >= start_local_date,
                        ChannelDailyChurn.snapshot_date <= today,
                    )
                    .one()
                )
                try:
                    total_joins_by_h[h] += int(joins_sum or 0)
                    total_leaves_by_h[h] += int(leaves_sum or 0)
                except Exception:
                    pass
                parts.append(
                    f"{h}ч: 📝 {cnt_int} | 👀 {avg_int} | ER {er_txt} | ⬆️ {int(joins_sum or 0)} | ⬇️ {int(leaves_sum or 0)}"
                )
            lines.append("\n".join(parts))

        header_lines: list[str] = ["<b>ИТОГО по каналам</b>", f"👥 {total_subs}"]
        for h in horizons:
            total_views = int(total_views_by_h.get(h, 0) or 0)
            total_joins = int(total_joins_by_h.get(h, 0) or 0)
            total_leaves = int(total_leaves_by_h.get(h, 0) or 0)
            er_total_txt = "-"
            if total_subs > 0 and total_views > 0:
                er_total = (float(total_views) / float(total_subs)) * 100.0
                er_total_txt = f"{er_total:.1f}%"
            header_lines.append(
                f"{h}ч: 👀 {total_views} | ER {er_total_txt} | ⬆️ {total_joins} | ⬇️ {total_leaves}"
            )

        return "\n".join(header_lines) + "\n\n" + "\n\n".join(lines)


async def notify_daily_stats(bot: Bot) -> None:
    text = await build_stats_report_text()
    with session_scope() as s:
        user_ids = [
            row.tg_user_id for row in s.query(User).filter(User.notify_daily_stats.is_(True)).all()
        ]
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to send daily stats to %s", uid)
