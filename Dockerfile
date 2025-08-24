# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base

# Опции Python/Pip для контейнера
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Системные зависимости (минимум)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь
RUN useradd -m -u 10001 bot
WORKDIR /app

# Если у тебя pyproject.toml — раскомментируй блок ниже и закомментируй requirements.txt
# COPY pyproject.toml poetry.lock* /app/
# RUN pip install --upgrade pip && pip install poetry && poetry config virtualenvs.create false \
#     && poetry install --no-interaction --no-ansi --only main

# requirements.txt путь по умолчанию
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем исходники
COPY --chown=bot:bot app/ /app/app

# Переключаем пользователя
USER bot

# По желанию: выставь свой TZ через переменную окружения
ENV TZ=Europe/Moscow

# Если у тебя точка входа другая — поменяй на свой модуль/файл
CMD ["python", "-m", "app.main"]