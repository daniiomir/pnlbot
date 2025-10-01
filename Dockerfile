FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales tzdata gcc \
    && rm -rf /var/lib/apt/lists/* \
    && echo "Europe/Moscow" > /etc/timezone \
    && dpkg-reconfigure -f noninteractive tzdata \
    && sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY bot.py ./bot.py

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -e .

RUN useradd -m appuser
USER appuser

ENTRYPOINT ["python", "bot.py"]
