# Базовый образ Python
FROM python:3.13-slim

# Рабочая директория в контейнере
WORKDIR /app

# Установим зависимости системы (если нужны)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта
COPY . .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Загружаем переменные окружения
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "bot.py"]
