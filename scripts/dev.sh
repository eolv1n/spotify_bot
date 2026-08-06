#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/deploy/docker-compose.dev.yml"

cd "$PROJECT_ROOT"

if (($# == 0)); then
  set -- up -d --build
fi

exec docker compose -f "$COMPOSE_FILE" "$@"
