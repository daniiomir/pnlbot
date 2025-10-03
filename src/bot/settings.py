from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from urllib.parse import quote_plus
from typing import Set
from logging.handlers import RotatingFileHandler


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
    telethon_api_id: int
    telethon_api_hash: str
    telethon_session_path: str
    telethon_session_string: str | None

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
        telethon_api_id_str = _get_env("TELETHON_API_ID", required=True)
        if not telethon_api_id_str.isdigit():
            raise RuntimeError("TELETHON_API_ID должен быть числом")
        telethon_api_id = int(telethon_api_id_str)
        telethon_api_hash = _get_env("TELETHON_API_HASH", required=True)
        telethon_session_path = _get_env("TELETHON_SESSION_PATH", default="telethon.session")
        telethon_session_string = _get_env("TELETHON_SESSION_STRING", default="").strip() or None
        return cls(
            bot_token=bot_token,
            database_url=database_url,
            whitelist_user_ids=whitelist_user_ids,
            tz=tz,
            log_level=log_level,
            telethon_api_id=telethon_api_id,
            telethon_api_hash=telethon_api_hash,
            telethon_session_path=telethon_session_path,
            telethon_session_string=telethon_session_string,
        )


def setup_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    class _MaxLevelFilter(logging.Filter):
        def __init__(self, max_level: int) -> None:
            super().__init__()
            self.max_level = max_level

        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            return record.levelno < self.max_level

    # stdout handler: only logs below ERROR
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)
    stdout_handler.addFilter(_MaxLevelFilter(logging.ERROR))

    # stderr handler: ERROR and above
    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.ERROR)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)

    # Optional file handler
    log_file = os.environ.get("LOG_FILE", "").strip()
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            root.addHandler(file_handler)
        except Exception:
            # If file logging fails, continue without breaking the app
            root.exception("Failed to initialize file logger: %s", log_file)

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
