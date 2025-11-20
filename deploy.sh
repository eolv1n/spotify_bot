#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$HOME/spotify_bot"
IMAGE_NAME="spotify_bot"

echo "🚀 Деплой Spotify Bot"
echo "📍 Репозиторий: $REPO_DIR"
echo "📅 Дата: $(date)"
echo "---------------------------------------------"

cd "$REPO_DIR" || { echo "❌ Не удалось перейти в $REPO_DIR"; exit 1; }

# 1. Опциональный health-check сервера
if [[ -x "./server_check.sh" ]]; then
  echo "🧭 Запускаем server_check.sh..."
  ./server_check.sh
  echo "✅ server_check.sh завершился успешно"
  echo "---------------------------------------------"
else
  echo "ℹ️ server_check.sh не найден — пропускаем проверку сервера"
fi

# 2. Обновляем код
echo "📥 Обновляем main из GitHub..."
git pull --ff-only origin main
echo "---------------------------------------------"

# 3. Версия по коммиту
VERSION="$(git rev-parse --short HEAD)"
echo "🏷 Версия (git SHA): $VERSION"

# 4. Сохраняем предыдущий образ для возможного отката
if docker image inspect "${IMAGE_NAME}:latest" >/dev/null 2>&1; then
  echo "💾 Сохраняем предыдущий образ как ${IMAGE_NAME}:prev"
  docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:prev"
else
  echo "ℹ️ Образ ${IMAGE_NAME}:latest ещё не существует — откатываться пока не к чему"
fi
echo "---------------------------------------------"

# 5. Собираем новый образ
echo "🐳 Сборка Docker-образа..."
docker build \
  -t "${IMAGE_NAME}:${VERSION}" \
  -t "${IMAGE_NAME}:latest" \
  .

echo "✅ Образ собран: ${IMAGE_NAME}:${VERSION}"
echo "---------------------------------------------"

# 6. Останавливаем и удаляем старый контейнер
echo "🛑 Останавливаем и удаляем старый контейнер (если есть)..."
docker rm -f "${IMAGE_NAME}" 2>/dev/null || true

# 7. Запускаем новый контейнер с лимитами ресурсов
echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name "${IMAGE_NAME}" \
  --env-file .env \
  --restart unless-stopped \
  --memory=300m \
  --cpus=0.5 \
  "${IMAGE_NAME}:latest"

echo "⏳ Ждём 5 секунд, даём контейнеру подняться..."
sleep 5
echo "---------------------------------------------"

# 8. Проверяем, что контейнер жив
if ! docker ps --format '{{.Names}}' | grep -qx "${IMAGE_NAME}"; then
  echo "❌ Новый контейнер ${IMAGE_NAME} не запустился."
  echo "📜 Логи неудачного запуска:"
  docker logs "${IMAGE_NAME}" || true

  echo "🧹 Удаляем неудачный контейнер..."
  docker rm -f "${IMAGE_NAME}" || true

  # 9. Пытаемся откатиться
  if docker image inspect "${IMAGE_NAME}:prev" >/dev/null 2>&1; then
    echo "♻️ Выполняем rollback из ${IMAGE_NAME}:prev..."
    docker run -d \
      --name "${IMAGE_NAME}" \
      --env-file .env \
      --restart unless-stopped \
      --memory=300m \
      --cpus=0.5 \
      "${IMAGE_NAME}:prev"

    echo "✅ Откат завершён, контейнер запущен из ${IMAGE_NAME}:prev"
    docker ps | grep "${IMAGE_NAME}" || true
    exit 1
  else
    echo "⚠️ Нет предыдущего образа ${IMAGE_NAME}:prev — нужен ручной разбор."
    exit 1
  fi
fi

echo "✅ Новый контейнер ${IMAGE_NAME} успешно запущен!"
docker ps | grep "${IMAGE_NAME}" || true

echo "📜 Последние логи:"
docker logs --tail=20 "${IMAGE_NAME}" || true

echo "🎉 Деплой завершён успешно"
