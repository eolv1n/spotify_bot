#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
IMAGE_NAME="${IMAGE_NAME:-spotify_bot}"
BOT_CONTAINER_NAME="${BOT_CONTAINER_NAME:-spotify_bot}"
WG_CONTAINER_NAME="${WG_CONTAINER_NAME:-spotify_bot_wg}"
RUNTIME_DIR="${RUNTIME_DIR:-$HOME/spotify_bot_runtime}"
BOT_ENV_FILE="${BOT_ENV_FILE:-$RUNTIME_DIR/bot.env}"
BOT_CACHE_DIR="${BOT_CACHE_DIR:-$RUNTIME_DIR/cache}"
WG_CONFIG_DIR="${WG_CONFIG_DIR:-$RUNTIME_DIR/wireguard}"
WG_CONFIG_PATH="$WG_CONFIG_DIR/wg_confs/wg0.conf"
REPO_REF="${REPO_REF:-main}"

echo "🚀 Деплой Spotify Bot"
echo "📍 Репозиторий: $REPO_DIR"
echo "🧩 env-файл: $BOT_ENV_FILE"
echo "💾 cache-dir: $BOT_CACHE_DIR"
echo "📡 WireGuard runtime: $WG_CONFIG_DIR"
echo "📅 Дата: $(date)"
echo "---------------------------------------------"

cd "$REPO_DIR" || { echo "❌ Не удалось перейти в каталог $REPO_DIR"; exit 1; }

if ! docker compose version >/dev/null 2>&1; then
  echo "❌ docker compose не найден. Установи Docker Compose plugin на сервере."
  exit 1
fi

# 1. Health-check сервера (если есть скрипт)
if [[ -x "./server_check.sh" ]]; then
  echo "🧭 Запускаем server_check.sh..."
  ./server_check.sh
  echo "✅ server_check.sh завершился успешно"
else
  echo "ℹ️ server_check.sh не найден или не исполняемый — пропускаем"
fi

echo "---------------------------------------------"
echo "📥 Обновляем $REPO_REF из GitHub..."
git fetch origin "$REPO_REF"
git checkout "$REPO_REF"
git pull --ff-only origin "$REPO_REF"

mkdir -p "$BOT_CACHE_DIR" "$WG_CONFIG_DIR/wg_confs"

if [[ ! -f "$BOT_ENV_FILE" ]]; then
  echo "❌ Не найден env-файл: $BOT_ENV_FILE"
  echo "ℹ️ Создай его на основе шаблона:"
  echo "   cp $REPO_DIR/.env.example $BOT_ENV_FILE"
  exit 1
fi

if [[ ! -f "$WG_CONFIG_PATH" ]]; then
  echo "❌ Не найден WireGuard-конфиг: $WG_CONFIG_PATH"
  echo "ℹ️ Создай его командой:"
  echo "   cp $REPO_DIR/deploy/wireguard/wg_confs/wg0.conf.example $WG_CONFIG_PATH"
  echo "ℹ️ Затем заполни своими ключами и endpoint."
  exit 1
fi

export BOT_ENV_FILE BOT_CACHE_DIR WG_CONFIG_DIR

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
docker compose up -d --force-recreate wireguard spotify_bot

echo "⏳ Ждём 5 секунд, даём контейнеру подняться..."
sleep 5
echo "---------------------------------------------"

echo "🔍 Проверяем, что контейнеры запущены..."
BOT_RUNNING="$(docker inspect -f '{{.State.Running}}' "${BOT_CONTAINER_NAME}" 2>/dev/null || true)"
WG_RUNNING="$(docker inspect -f '{{.State.Running}}' "${WG_CONTAINER_NAME}" 2>/dev/null || true)"

if [[ "$BOT_RUNNING" != "true" || "$WG_RUNNING" != "true" ]]; then
  echo "❌ Один или оба контейнера не запустились."
  echo "📜 Логи wireguard:"
  docker logs --tail=80 "${WG_CONTAINER_NAME}" || true
  echo "📜 Логи spotify_bot:"
  docker logs --tail=80 "${BOT_CONTAINER_NAME}" || true

  if docker image inspect "${IMAGE_NAME}:prev" >/dev/null 2>&1; then
    echo "♻️ Выполняем rollback bot-образа на ${IMAGE_NAME}:prev"
    docker tag "${IMAGE_NAME}:prev" "${IMAGE_NAME}:latest"
    docker compose up -d --force-recreate spotify_bot
    echo "⚠️ Бот откатан на предыдущий образ. WireGuard-конфиг при этом не откатывается."
  else
    echo "⚠️ Нет образа ${IMAGE_NAME}:prev для отката. Требуется ручное вмешательство."
  fi

  exit 1
fi

echo "✅ Контейнеры успешно запущены"
docker compose ps

echo "🧭 Проверка внешнего WG runtime:"
ls -la "$WG_CONFIG_DIR" "$WG_CONFIG_DIR/wg_confs" || true

echo "📜 Последние логи WireGuard:"
docker logs --tail=20 "${WG_CONTAINER_NAME}" || true
echo "📜 Последние логи бота:"
docker logs --tail=20 "${BOT_CONTAINER_NAME}" || true

echo "🎉 Деплой завершён успешно"
