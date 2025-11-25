# Базовый образ Python
FROM python:3.13-slim

# Рабочая директория в контейнере
WORKDIR /app

# Минимум системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Сначала только зависимости — ради кэша
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Потом уже весь код
COPY . .

# Логи без буфера
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "bot.py"]
