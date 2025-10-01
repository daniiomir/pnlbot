from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Set


def _parse_whitelist(value: str | None) -> Set[int]:
    if not value:
        return set()
    result: Set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"WHITELIST_USER_IDS содержит нечисловой id: {part}")
        result.add(int(part))
    return result


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Отсутствует обязательная переменная окружения: {name}")
    return val or ""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    whitelist_user_ids: Set[int]
    tz: str
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        bot_token = _get_env("BOT_TOKEN", required=True)
        # Compose DSN from separate env vars
        db_host = _get_env("DB_HOST", required=True)
        db_port = _get_env("DB_PORT", default="5432")
        db_name = _get_env("DB_NAME", required=True)
        db_user = _get_env("DB_USER", required=True)
        db_password = _get_env("DB_PASSWORD", required=True)
        if not db_port.isdigit():
            raise RuntimeError("DB_PORT должен быть числом")
        database_url = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        whitelist_user_ids = _parse_whitelist(_get_env("WHITELIST_USER_IDS", required=True))
        tz = _get_env("TZ", default="Europe/Moscow")
        log_level = _get_env("LOG_LEVEL", default="INFO").upper()
        return cls(
            bot_token=bot_token,
            database_url=database_url,
            whitelist_user_ids=whitelist_user_ids,
            tz=tz,
            log_level=log_level,
        )


def setup_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(stream_handler)

    # Ensure verbose logs from aiogram are visible
    for logger_name in (
        "aiogram",
        "aiogram.event",
        "aiogram.dispatcher",
        "aiogram.bot.api",
    ):
        logging.getLogger(logger_name).setLevel(level)

    # Route warnings through logging
    logging.captureWarnings(True)


__all__ = ["Settings", "setup_logging"]
