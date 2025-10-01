from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from urllib.parse import quote_plus
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


def _normalize_host_port(host: str, port: str) -> tuple[str, str]:
    """Return sanitized host and port.

    - Strips leading '@' sometimes mistakenly included in env vars
    - If host contains ":<digits>" and explicit port not provided (or is default),
      extract the port from host to avoid duplicates
    """
    sanitized_host = host.lstrip("@").strip()
    sanitized_port = (port or "").strip()

    # Try to extract port embedded in host, prefer explicit non-default port
    if ":" in sanitized_host:
        maybe_host, maybe_port = sanitized_host.rsplit(":", 1)
        if maybe_port.isdigit() and (not sanitized_port or sanitized_port == "5432"):
            sanitized_host = maybe_host
            sanitized_port = maybe_port

    return sanitized_host, sanitized_port or "5432"


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

        # Prefer DATABASE_URL if explicitly provided
        database_url = _get_env("DATABASE_URL", default="").strip()
        if not database_url:
            # Compose DSN from separate env vars
            db_host = _get_env("DB_HOST", required=True)
            db_port = _get_env("DB_PORT", default="5432")
            db_name = _get_env("DB_NAME", required=True)
            db_user = _get_env("DB_USER", required=True)
            db_password = _get_env("DB_PASSWORD", required=True)

            norm_host, norm_port = _normalize_host_port(db_host, db_port)
            if not norm_port.isdigit():
                raise RuntimeError("DB_PORT должен быть числом")

            # URL-encode credentials in case of special characters
            enc_user = quote_plus(db_user)
            enc_password = quote_plus(db_password)

            database_url = (
                f"postgresql+psycopg://{enc_user}:{enc_password}@{norm_host}:{norm_port}/{db_name}"
            )

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
