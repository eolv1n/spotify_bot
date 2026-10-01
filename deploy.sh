#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
IMAGE_NAME="${IMAGE_NAME:-spotify_bot}"
BOT_CONTAINER_NAME="${BOT_CONTAINER_NAME:-spotify_bot}"
RUNTIME_DIR="${RUNTIME_DIR:-$HOME/spotify_bot_runtime}"
BOT_ENV_FILE="${BOT_ENV_FILE:-$RUNTIME_DIR/bot.env}"
BOT_CACHE_DIR="${BOT_CACHE_DIR:-$RUNTIME_DIR/cache}"
REPO_REF="${REPO_REF:-main}"

umask 077

rollback_bot_image() {
  if docker image inspect "${IMAGE_NAME}:prev" >/dev/null 2>&1; then
    echo "♻️ Возвращаем bot-образ на ${IMAGE_NAME}:prev"
    docker tag "${IMAGE_NAME}:prev" "${IMAGE_NAME}:latest"
    docker compose up -d --force-recreate spotify_bot
    if ./scripts/prod_smoke.sh; then
      echo "✅ Предыдущий bot-образ восстановлен и прошёл smoke"
    else
      echo "❌ Предыдущий bot-образ не восстановил полный runtime contract"
    fi
  else
    echo "⚠️ Нет образа ${IMAGE_NAME}:prev для rollback. Требуется ручное вмешательство."
  fi
}

echo "🚀 Деплой Spotify Bot"
echo "📍 Репозиторий: $REPO_DIR"
echo "🧩 env-файл: $BOT_ENV_FILE"
echo "💾 cache-dir: $BOT_CACHE_DIR"
echo "📅 Дата: $(date)"
echo "---------------------------------------------"

cd "$REPO_DIR" || { echo "❌ Не удалось перейти в каталог $REPO_DIR"; exit 1; }

if ! docker compose version >/dev/null 2>&1; then
  echo "❌ docker compose не найден. Установи Docker Compose plugin на сервере."
  exit 1
fi

# 1. Health-check сервера (если есть скрипт)
if [[ -x "./scripts/server_check.sh" ]]; then
  echo "🧭 Запускаем scripts/server_check.sh..."
  ./scripts/server_check.sh
  echo "✅ scripts/server_check.sh завершился успешно"
else
  echo "ℹ️ scripts/server_check.sh не найден или не исполняемый — пропускаем"
fi

echo "---------------------------------------------"
echo "📥 Обновляем $REPO_REF из GitHub..."
git fetch origin "$REPO_REF"
git checkout "$REPO_REF"
git pull --ff-only origin "$REPO_REF"

mkdir -p "$BOT_CACHE_DIR"

if [[ ! -f "$BOT_ENV_FILE" ]]; then
  echo "❌ Не найден env-файл: $BOT_ENV_FILE"
  echo "ℹ️ Создай его на основе шаблона:"
  echo "   cp $REPO_DIR/.env.example $BOT_ENV_FILE"
  exit 1
fi

# Production requires an explicit Yandex route; never fall back silently.
if ! grep -Eq '^YANDEX_PROXY_URL=https?://[^[:space:]]+' "$BOT_ENV_FILE"; then
  echo "❌ YANDEX_PROXY_URL must configure a private HTTP proxy in runtime env"
  exit 1
fi
chmod 600 "$BOT_ENV_FILE"
export BOT_ENV_FILE BOT_CACHE_DIR
export PROD_BOT_ENV_FILE="$BOT_ENV_FILE"
export PROD_BOT_CACHE_DIR="$BOT_CACHE_DIR"

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
echo "🐳 Сборка Docker-образа через docker compose..."

docker compose build spotify_bot
docker image tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${VERSION}"

echo "✅ Образ собран: ${IMAGE_NAME}:${VERSION}"
echo "---------------------------------------------"

echo "🚀 Пересоздаём контейнеры через docker compose..."
docker compose up -d --force-recreate spotify_bot

echo "⏳ Ждём 5 секунд, даём контейнеру подняться..."
sleep 5
echo "---------------------------------------------"

echo "🔍 Проверяем, что контейнеры запущены..."
BOT_RUNNING="$(docker inspect -f '{{.State.Running}}' "${BOT_CONTAINER_NAME}" 2>/dev/null || true)"

if [[ "$BOT_RUNNING" != "true" ]]; then
  echo "❌ Контейнер бота не запустился."
  echo "📜 Логи spotify_bot:"
  docker logs --tail=80 "${BOT_CONTAINER_NAME}" || true

  rollback_bot_image

  exit 1
fi

echo "✅ Контейнеры успешно запущены"
docker compose ps

echo "📜 Последние логи бота:"
docker logs --tail=20 "${BOT_CONTAINER_NAME}" || true

echo "🧪 Выполняем production smoke contract..."
if ! ./scripts/prod_smoke.sh; then
  echo "❌ Production smoke не прошёл"
  echo "📜 Последние логи бота:"
  docker logs --tail=80 "${BOT_CONTAINER_NAME}" || true
  rollback_bot_image
  exit 1
fi

echo "🎉 Деплой завершён успешно"
