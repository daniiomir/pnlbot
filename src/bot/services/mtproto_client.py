from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

from bot.settings import Settings

logger = logging.getLogger()


_client: Optional[TelegramClient] = None


async def init_telethon(settings: Settings) -> TelegramClient:
    global _client
    if _client is not None:
        return _client
    # Require StringSession from env; no fallbacks
    if not settings.telethon_session_string:
        raise RuntimeError("TELETHON_SESSION_STRING is required and must be set")
    session = StringSession(settings.telethon_session_string)
    client = TelegramClient(session, settings.telethon_api_id, settings.telethon_api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Telethon session is not authorized. Interactive login is required to proceed.")
        # We do not perform interactive login here; provide session separately if needed
    _client = client
    logger.info("Telethon client initialized")
    return client


def get_telethon() -> TelegramClient:
    if _client is None:
        raise RuntimeError("Telethon client is not initialized")
    return _client


async def shutdown_telethon() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.disconnect()
    except Exception:
        logger.exception("Failed to disconnect Telethon client")
    finally:
        _client = None


