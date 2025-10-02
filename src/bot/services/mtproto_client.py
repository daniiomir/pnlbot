from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient

from bot.settings import Settings

logger = logging.getLogger(__name__)


_client: Optional[TelegramClient] = None


async def init_telethon(settings: Settings) -> TelegramClient:
    global _client
    if _client is not None:
        return _client
    client = TelegramClient(settings.telethon_session_path, settings.telethon_api_id, settings.telethon_api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Telethon session is not authorized. Please login the session out-of-band.")
        # We do not perform interactive login here; require pre-authorized session file
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


