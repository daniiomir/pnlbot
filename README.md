# Finance Bot (RUB, Europe/Moscow)

Телеграм-бот для внесения операций доходов/расходов в PostgreSQL.

## Переменные окружения
- `BOT_TOKEN` — токен бота
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — параметры подключения к PostgreSQL
- `WHITELIST_USER_IDS` — список user_id через запятую
- `TZ` — `Europe/Moscow` (по умолчанию)
- `LOG_LEVEL` — по умолчанию `INFO`

## Установка и запуск локально
```
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
export BOT_TOKEN=***
export DB_HOST=host
export DB_PORT=5432
export DB_NAME=db
export DB_USER=user
export DB_PASSWORD=pass
export WHITELIST_USER_IDS="12345,67890"
export TZ=Europe/Moscow
alembic upgrade head
PYTHONPATH=src python -m bot.main
```

## Docker
Сборка образа:
```
docker build -t finance-bot:latest .
```
Запуск:
```
docker run --rm \
  -e BOT_TOKEN=*** \
  -e DB_HOST=host \
  -e DB_PORT=5432 \
  -e DB_NAME=db \
  -e DB_USER=user \
  -e DB_PASSWORD=pass \
  -e WHITELIST_USER_IDS="12345,67890" \
  -e TZ=Europe/Moscow \
  finance-bot:latest
```
