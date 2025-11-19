#!/bin/bash
set -e  # Остановить выполнение при любой ошибке

echo "🚀 Обновляем Spotify Bot..."

cd ~/spotify_bot || { echo "❌ Не удалось перейти в каталог ~/spotify_bot"; exit 1; }

echo "📥 Тянем последние изменения из main..."
git pull origin main

echo "🐳 Пересобираем Docker-образ..."
docker build -t spotify_bot .

# Проверяем, есть ли запущенный контейнер
if [ "$(docker ps -q -f name=spotify_bot)" ]; then
    echo "🛑 Останавливаем текущий контейнер..."
    docker stop spotify_bot

    echo "⏳ Ждём остановки контейнера..."
    docker wait spotify_bot || true
fi

# Проверяем, существует ли контейнер (даже если он не запущен)
if [ "$(docker ps -aq -f name=spotify_bot)" ]; then
    echo "🗑 Удаляем старый контейнер..."
    docker rm spotify_bot
fi

echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name spotify_bot \
  --env-file .env \
  --restart unless-stopped \
  spotify_bot:latest

echo "✅ Новый контейнер запущен!"
docker ps | grep spotify_bot

echo "📜 Последние логи:"
docker logs --tail=10 spotify_bot
