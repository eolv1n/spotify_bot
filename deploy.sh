#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$HOME/spotify_bot"
CONTAINER_NAME="spotify_bot"
IMAGE_NAME="spotify_bot"

echo "🚀 Деплой Spotify Bot"
echo "📍 Репозиторий: $REPO_DIR"
echo "📅 Дата: $(date)"
echo "---------------------------------------------"

cd "$REPO_DIR" || { echo "❌ Не удалось перейти в каталог $REPO_DIR"; exit 1; }

# 1. Health-check сервера (если есть скрипт)
if [[ -x "./server_check.sh" ]]; then
  echo "🧭 Запускаем server_check.sh..."
  ./server_check.sh
  echo "✅ server_check.sh завершился успешно"
else
  echo "ℹ️ server_check.sh не найден или не исполняемый — пропускаем"
fi

echo "---------------------------------------------"
echo "📥 Обновляем main из GitHub..."
git fetch origin main
git reset --hard origin/main

VERSION="$(git rev-parse --short HEAD)"
echo "🏷 Версия (git SHA): $VERSION"

# 2. Сохраняем предыдущий образ для rollback
if docker image inspect "${IMAGE_NAME}:latest" >/dev/null 2>&1; then
  echo "💾 Сохраняем предыдущий образ как ${IMAGE_NAME}:prev"
  docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:prev"
else
  echo "ℹ️ Образ ${IMAGE_NAME}:latest ещё не существует — откатываться пока не к чему"
fi

echo "---------------------------------------------"
echo "🐳 Сборка Docker-образа..."

docker build \
  -t "${IMAGE_NAME}:${VERSION}" \
  -t "${IMAGE_NAME}:latest" \
  .

echo "✅ Образ собран: ${IMAGE_NAME}:${VERSION}"
echo "---------------------------------------------"

echo "🛑 Останавливаем и удаляем старый контейнер (если есть)..."
if docker ps -a -q -f "name=^${CONTAINER_NAME}$" >/dev/null; then
  docker rm -f "${CONTAINER_NAME}" || true
fi

echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  --env-file .env \
  --restart unless-stopped \
  --memory=300m \
  --cpus=0.5 \
  "${IMAGE_NAME}:latest"

echo "⏳ Ждём 5 секунд, даём контейнеру подняться..."
sleep 5
echo "---------------------------------------------"

echo "🔍 Проверяем, что контейнер запущен..."
if ! docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null | grep -q true; then
  echo "❌ Новый контейнер ${CONTAINER_NAME} не запустился или сразу упал."
  echo "📜 Логи неудачного запуска:"
  docker logs --tail=50 "${CONTAINER_NAME}" || true

  echo "🧹 Удаляем неуспешный контейнер..."
  docker rm -f "${CONTAINER_NAME}" || true

  if docker image inspect "${IMAGE_NAME}:prev" >/dev/null 2>&1; then
    echo "♻️ Выполняем rollback: запускаем контейнер из ${IMAGE_NAME}:prev"
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --env-file .env \
      --restart unless-stopped \
      --memory=300m \
      --cpus=0.5 \
      "${IMAGE_NAME}:prev"

    echo "✅ Откат завершён, контейнер запущен из ${IMAGE_NAME}:prev"
    docker ps | grep "${CONTAINER_NAME}" || true
    exit 1
  else
    echo "⚠️ Нет образа ${IMAGE_NAME}:prev для отката. Требуется ручное вмешательство."
    exit 1
  fi
fi

echo "✅ Новый контейнер ${CONTAINER_NAME} успешно запущен!"
docker ps | grep "${CONTAINER_NAME}" || true

echo "📜 Последние логи:"
docker logs --tail=20 "${CONTAINER_NAME}" || true

echo "🎉 Деплой завершён успешно"
