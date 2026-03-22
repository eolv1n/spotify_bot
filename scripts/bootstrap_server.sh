#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="${1:-$PROJECT_ROOT/deploy/install.conf}"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

REPO_URL="${REPO_URL:-https://github.com/eolv1n/spotify_bot.git}"
REPO_REF="${REPO_REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/spotify_bot}"
RUNTIME_DIR="${RUNTIME_DIR:-/opt/spotify_bot_runtime}"
BOT_ENV_FILE="${BOT_ENV_FILE:-$RUNTIME_DIR/bot.env}"
BOT_CACHE_DIR="${BOT_CACHE_DIR:-$RUNTIME_DIR/cache}"
WG_CONFIG_DIR="${WG_CONFIG_DIR:-$RUNTIME_DIR/wireguard}"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
TZ="${TZ:-Europe/Moscow}"

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "❌ Запусти bootstrap от root: sudo bash scripts/bootstrap_server.sh"
    exit 1
  fi
}

install_docker_apt() {
  export DEBIAN_FRONTEND=noninteractive

  apt-get update
  local compose_package="docker-compose-plugin"

  if ! apt-cache show "$compose_package" >/dev/null 2>&1; then
    compose_package="docker-compose-v2"
  fi

  apt-get install -y ca-certificates curl git docker.io "$compose_package"
  systemctl enable --now docker
}

ensure_prerequisites() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "✅ Docker и docker compose уже доступны"
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    echo "📦 Устанавливаю Docker, compose plugin и Git через apt"
    install_docker_apt
    return
  fi

  echo "❌ Автоустановка поддержана только для Debian/Ubuntu через apt."
  echo "ℹ️ Установи Docker, docker compose и Git вручную, затем повтори запуск."
  exit 1
}

sync_repo() {
  mkdir -p "$(dirname "$INSTALL_DIR")"

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "📥 Обновляю репозиторий в $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin "$REPO_REF"
    git -C "$INSTALL_DIR" checkout "$REPO_REF"
    git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_REF"
  else
    echo "📥 Клонирую репозиторий в $INSTALL_DIR"
    git clone --branch "$REPO_REF" "$REPO_URL" "$INSTALL_DIR"
  fi
}

prepare_runtime() {
  mkdir -p "$RUNTIME_DIR" "$BOT_CACHE_DIR" "$WG_CONFIG_DIR/wg_confs"

  if [[ ! -f "$BOT_ENV_FILE" ]]; then
    cp "$INSTALL_DIR/.env.example" "$BOT_ENV_FILE"
    echo "📝 Создан шаблон env: $BOT_ENV_FILE"
  fi

  if [[ ! -f "$WG_CONFIG_DIR/wg_confs/wg0.conf" ]]; then
    cp "$INSTALL_DIR/deploy/wireguard/wg_confs/wg0.conf.example" \
      "$WG_CONFIG_DIR/wg_confs/wg0.conf"
    echo "📝 Создан шаблон WireGuard: $WG_CONFIG_DIR/wg_confs/wg0.conf"
  fi
}

validate_runtime() {
  local env_missing=0

  if grep -Eq 'replace-me|^\s*TELEGRAM_TOKEN=\s*$|^\s*SPOTIFY_CLIENT_ID=\s*$|^\s*SPOTIFY_CLIENT_SECRET=\s*$' "$BOT_ENV_FILE"; then
    echo "⚠️ Заполни секреты в $BOT_ENV_FILE"
    env_missing=1
  fi

  if grep -Eq 'REPLACE_WITH_|your-home-endpoint\.example\.com' "$WG_CONFIG_DIR/wg_confs/wg0.conf"; then
    echo "⚠️ Проверь и заполни WireGuard-конфиг: $WG_CONFIG_DIR/wg_confs/wg0.conf"
    env_missing=1
  fi

  if [[ "$env_missing" -eq 1 ]]; then
    echo
    echo "ℹ️ После заполнения файлов повторно запусти:"
    echo "   sudo BOT_ENV_FILE=$BOT_ENV_FILE WG_CONFIG_DIR=$WG_CONFIG_DIR BOT_CACHE_DIR=$BOT_CACHE_DIR $INSTALL_DIR/deploy.sh"
    exit 0
  fi
}

run_deploy() {
  echo "🚀 Запускаю deploy.sh"
  export INSTALL_DIR RUNTIME_DIR BOT_ENV_FILE BOT_CACHE_DIR WG_CONFIG_DIR PUID PGID TZ
  bash "$INSTALL_DIR/deploy.sh"
}

require_root
ensure_prerequisites
sync_repo
prepare_runtime
validate_runtime
run_deploy
