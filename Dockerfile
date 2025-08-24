# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata curl build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 bot
WORKDIR /app

# Сначала копируем только pyproject.toml (чтобы кешировались зависимости)
COPY pyproject.toml /app/
COPY README.md /app/

RUN pip install --upgrade pip && pip install .

# Теперь копируем весь код
COPY --chown=bot:bot . /app

USER bot
ENV TZ=Europe/Moscow

CMD ["python", "-m", "app.main"]