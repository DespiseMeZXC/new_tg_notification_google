# Используем официальный образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PYTHONPATH=/app

# Устанавливаем зависимости, копируем файлы и настраиваем приложение
# не обязательно ставить всё это (оно уже с офиц образом стоит всё)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
#     && rm -rf /var/lib/apt/lists/* \
#     && mkdir -p /data

# Копируем бинарный файл uv из официального образа для более быстрой установки
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Копируем только файлы зависимостей для лучшего кэширования слоев
COPY pyproject.toml uv.lock ./
RUN touch README.md && uv sync --frozen

# Копируем код приложения
COPY . .

# Запускаем приложение
CMD ["uv", "run", "src/bot.py"]
