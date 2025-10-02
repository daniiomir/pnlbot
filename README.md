# Finance Bot (RUB, Europe/Moscow)

Телеграм-бот учёта доходов/расходов с хранением в PostgreSQL. Поддерживает выбор каналов, сумму с копейками, ссылку на чек и комментарий, а также дедупликацию операций. Дополнительно: управление каналами и ежедневный сбор фактических показателей каналов через Telethon (MTProto).

## Возможности

- Доходы/расходы по категориям и каналам (мультивыбор каналов)
- Сумма с копейками: `1200.50`, `1 200,50`, `1200,5`
- Необязательные поля: ссылка на чек (URL) и комментарий
- Дедупликация по окну 3 минуты (см. ниже)
- Вайтлист пользователей (работает только в личке)
- Логи только в консоль (stdout)
- Управление каналами: добавление по пересланному посту, список, пауза, удаление (только whitelist)
- Ежедневный сбор фактических показателей каналов через Telethon в 00:05 Europe/Moscow:
  - По каналу: число подписчиков (на момент сбора)
  - По постам за прошедшие сутки: просмотры (`views`), пересылки (`forwards`), суммарные реакции (`reactions_total`, если доступны)
  - Хранение «фактов» без агрегаций в БД: далее можно считать метрики SQL-запросами

## Команды бота

- `/start` — стартовое сообщение и подсказки
- `/help` — краткая справка
- `/add` — добавление операции пошагово
- `/in` — быстрый старт добавления дохода (сразу выбор категории)
- `/out` — быстрый старт добавления расхода (сразу выбор категории)
- `/cancel` — отмена текущей операции
- `/channels` — меню управления каналами (добавить по форварду, список, пауза/удалить)

## Логика дедупликации

Для защиты от повторных подтверждений вычисляется `dedup_hash` (SHA-256) из полей:

- `tg_user_id`, `op_type`, `category_code`, `amount_kop`, отсортированные уникальные `channel_ids`, `is_general`, и время, округлённое к началу текущего 3‑минутного окна.

Если в течение 3 минут поступят повторные подтверждения с тем же набором полей — сработает уникальный ключ, новая запись не создастся, пользователь увидит сообщение про дубликат.

## Переменные окружения

- `BOT_TOKEN` — токен бота
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — параметры PostgreSQL
- `WHITELIST_USER_IDS` — список user_id через запятую (доступ только из этого списка)
- `TZ` — часовой пояс, по умолчанию `Europe/Moscow`
- `LOG_LEVEL` — уровень логирования, по умолчанию `INFO`
- `TELETHON_API_ID` — API ID Telegram (my.telegram.org)
- `TELETHON_API_HASH` — API Hash Telegram (my.telegram.org)
- `TELETHON_SESSION_PATH` — путь к файлу сессии Telethon (по умолчанию `telethon.session`)

Альтернатива для БД: вместо `DB_HOST`/`DB_*` можно задать `DATABASE_URL` (например: `postgresql+psycopg://user:pass@host:5432/db`).

## Установка и запуск локально

```bash
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
export TELETHON_API_ID=123456
export TELETHON_API_HASH=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export TELETHON_SESSION_PATH=./telethon.session

# Миграции применяются автоматически при старте приложения.
# При желании можно выполнить вручную:
alembic upgrade head

PYTHONPATH=src python -m bot.main
```

Также можно воспользоваться Makefile:

```bash
make venv
make run
```

## Пример .env

Скопируйте `examples/env.example` в `.env` и заполните значения.

## Docker

Сборка образа:

```bash
docker build -t finance-bot:latest .
```

Запуск:

```bash
docker run --rm \
  -e BOT_TOKEN=*** \
  -e DB_HOST=host \
  -e DB_PORT=5432 \
  -e DB_NAME=db \
  -e DB_USER=user \
  -e DB_PASSWORD=pass \
  -e WHITELIST_USER_IDS="12345,67890" \
  -e TZ=Europe/Moscow \
  -e TELETHON_API_ID=123456 \
  -e TELETHON_API_HASH=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  -e TELETHON_SESSION_PATH=/data/telethon.session \
  -v $(pwd)/telethon.session:/data/telethon.session \
  finance-bot:latest
```

## Примечания

- Бот работает только в приватных чатах (Whitelist middleware).
- После шага выбора каналов — мультивыбор, выбранные помечаются галочкой, в сообщении показан список выбранных.
- В подтверждении выводится: тип, категория (по‑русски), сумма, каналы, а также чек/комментарий при наличии.

### Каналы и Telethon

- Добавление канала: отправьте `/channels` → «➕ Добавить канал», затем перешлите любой пост из канала.
- Для приватных каналов добавьте user‑сессию (аккаунт, под которым авторизован Telethon) в участники канала.
- Сбор фактов происходит ежедневно в 00:05 Europe/Moscow.

### Подготовка Telethon session

Сессию нужно авторизовать заранее (интерактивный вход вне бота). Пример скрипта авторизации:

```python
from telethon import TelegramClient

api_id = 123456
api_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
session_path = "./telethon.session"

client = TelegramClient(session_path, api_id, api_hash)

async def main():
    await client.start()
    print("Authorized:", await client.is_user_authorized())

with client:
    client.loop.run_until_complete(main())
```

Запустите его и пройдите код подтверждения. Полученный файл `telethon.session` укажите через `TELETHON_SESSION_PATH` (или смонтируйте в контейнер).
