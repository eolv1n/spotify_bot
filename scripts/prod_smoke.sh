#!/usr/bin/env bash
set -euo pipefail

BOT_CONTAINER_NAME="${BOT_CONTAINER_NAME:-spotify_bot}"
WG_CONTAINER_NAME="${WG_CONTAINER_NAME:-spotify_bot_wg}"
SMOKE_ATTEMPTS="${SMOKE_ATTEMPTS:-12}"
SMOKE_INTERVAL_SECONDS="${SMOKE_INTERVAL_SECONDS:-5}"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

check_runtime() {
  local bot_running wg_running wg_health bot_logs api_output handshake_output

  bot_running="$(docker inspect -f '{{.State.Running}}' "$BOT_CONTAINER_NAME" 2>/dev/null || true)"
  wg_running="$(docker inspect -f '{{.State.Running}}' "$WG_CONTAINER_NAME" 2>/dev/null || true)"
  wg_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$WG_CONTAINER_NAME" 2>/dev/null || true)"

  [[ "$bot_running" == "true" ]] || {
    log "FAIL bot container is not running"
    return 1
  }
  [[ "$wg_running" == "true" && "$wg_health" == "healthy" ]] || {
    log "FAIL WireGuard container state: running=$wg_running health=$wg_health"
    return 1
  }

  bot_logs="$(docker logs "$BOT_CONTAINER_NAME" 2>&1)" || {
    log "FAIL bot logs are unavailable"
    return 1
  }
  if ! grep -F 'Бот запущен и готов к работе' <<<"$bot_logs" >/dev/null; then
    log "FAIL polling startup marker is absent"
    return 1
  fi

  api_output="$(docker exec -i "$BOT_CONTAINER_NAME" python - <<'PY'
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import aiohttp


async def require_json(session, method, url, *, label, expected_key=None, **kwargs):
    async with session.request(method, url, **kwargs) as response:
        if response.status >= 400:
            raise RuntimeError(f"{label} returned HTTP {response.status}")
        payload = await response.json(content_type=None)
        if expected_key and not payload.get(expected_key):
            raise RuntimeError(f"{label} response does not contain {expected_key}=true")
        return payload


async def main():
    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        telegram_token = os.environ["TELEGRAM_TOKEN"]
        await require_json(
            session,
            "GET",
            f"https://api.telegram.org/bot{telegram_token}/getMe",
            label="Telegram getMe",
            expected_key="ok",
        )
        print("telegram_get_me=ok")

        spotify_payload = await require_json(
            session,
            "POST",
            "https://accounts.spotify.com/api/token",
            label="Spotify token exchange",
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(
                os.environ["SPOTIFY_CLIENT_ID"],
                os.environ["SPOTIFY_CLIENT_SECRET"],
            ),
        )
        if not spotify_payload.get("access_token"):
            raise RuntimeError("Spotify response does not contain access_token")
        print("spotify_token=ok")

        async with session.get("https://music.yandex.ru") as response:
            if response.status >= 400:
                raise RuntimeError(f"Yandex Music returned HTTP {response.status}")
        print("yandex_https=ok")

    cache_path = Path(os.environ.get("CACHE_DB_PATH", "cache/music_cache.sqlite3"))
    if not cache_path.is_absolute():
        cache_path = Path("/app") / cache_path
    with sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True) as database:
        result = database.execute("PRAGMA quick_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError("SQLite PRAGMA quick_check failed")
    print("sqlite_quick_check=ok")


try:
    asyncio.run(main())
except Exception as error:
    print(f"runtime_probe_error={type(error).__name__}", file=sys.stderr)
    raise SystemExit(1)
PY
)" || {
    log "FAIL runtime API or SQLite probe failed"
    return 1
  }

  for marker in \
    telegram_get_me=ok \
    spotify_token=ok \
    yandex_https=ok \
    sqlite_quick_check=ok; do
    grep -qx "$marker" <<<"$api_output" || {
      log "FAIL missing smoke marker: $marker"
      return 1
    }
  done

  docker exec "$WG_CONTAINER_NAME" wg show wg0 >/dev/null
  handshake_output="$(docker exec "$WG_CONTAINER_NAME" wg show wg0 latest-handshakes)"
  awk '$2 > 0 { found=1 } END { exit !found }' <<<"$handshake_output" || {
    log "FAIL WireGuard has no completed handshake"
    return 1
  }

  log "OK polling, Telegram, Spotify, Yandex, SQLite and WireGuard smoke passed"
}

case "$SMOKE_ATTEMPTS" in
  ''|*[!0-9]*|0)
    echo "SMOKE_ATTEMPTS must be a positive integer" >&2
    exit 2
    ;;
esac

for attempt in $(seq 1 "$SMOKE_ATTEMPTS"); do
  if check_runtime; then
    exit 0
  fi
  if [[ "$attempt" -lt "$SMOKE_ATTEMPTS" ]]; then
    log "Retrying production smoke: attempt=$attempt/$SMOKE_ATTEMPTS"
    sleep "$SMOKE_INTERVAL_SECONDS"
  fi
done

log "FAIL production smoke exhausted attempts=$SMOKE_ATTEMPTS"
exit 1
