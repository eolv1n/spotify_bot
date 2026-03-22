#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/eolv1n/spotify_bot.git}"
REPO_REF="${REPO_REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/spotify_bot}"
BOOTSTRAP_CONFIG_PATH="${BOOTSTRAP_CONFIG_PATH:-}"

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "❌ Запусти установку от root, например:"
    echo "   curl -fsSL https://raw.githubusercontent.com/eolv1n/spotify_bot/main/install.sh | sudo bash"
    exit 1
  fi
}

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y git
    return
  fi

  echo "❌ git не найден, а автоустановка поддержана только для Debian/Ubuntu через apt."
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

run_bootstrap() {
  export REPO_URL REPO_REF INSTALL_DIR

  if [[ -n "$BOOTSTRAP_CONFIG_PATH" ]]; then
    bash "$INSTALL_DIR/scripts/bootstrap_server.sh" "$BOOTSTRAP_CONFIG_PATH"
  else
    bash "$INSTALL_DIR/scripts/bootstrap_server.sh"
  fi
}

require_root
ensure_git
sync_repo
run_bootstrap
