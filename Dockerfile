# Базовый образ Python
FROM python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

# Рабочая директория в контейнере
WORKDIR /app

# Минимум системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

# Сначала только зависимости — ради кэша
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Копируем только runtime-код: build context не должен включать секреты.
COPY --chown=app:app app ./app
COPY --chown=app:app bot.py .

# Логи без буфера
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

# Запуск бота
CMD ["python", "bot.py"]
