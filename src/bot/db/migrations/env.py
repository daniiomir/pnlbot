from __future__ import annotations

import os
import sys
import importlib.util
from logging.config import fileConfig

# Ensure src/ on path
SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# Load .env from project root if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(SRC_PATH), ".env"))
except Exception:
    pass

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Load models module explicitly from file to avoid name collision with root-level bot.py
MODELS_PATH = os.path.join(SRC_PATH, "bot", "db", "models.py")
spec = importlib.util.spec_from_file_location("app_models", MODELS_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load models module for Alembic")
models = importlib.util.module_from_spec(spec)
# Register module so SQLAlchemy can resolve typing annotations against module name
sys.modules["app_models"] = models
spec.loader.exec_module(models)  # type: ignore[arg-type]
Base = models.Base  # type: ignore[attr-defined]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    host = os.getenv("DB_HOST")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    if host and name and user and password:
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
    raise RuntimeError(
        "Не задана строка подключения к БД. Укажите DATABASE_URL или DB_HOST, DB_NAME, DB_USER, DB_PASSWORD (и DB_PORT)."
    )


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="finance",
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    url = get_url()
    if url:
        configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="finance",
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS finance"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
