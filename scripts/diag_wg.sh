#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "== docker compose ps =="
docker compose ps

echo
echo "== wireguard: wg show =="
docker compose exec -T wireguard wg show || true

echo
echo "== wireguard: ip address =="
docker compose exec -T wireguard ip address || true

echo
echo "== wireguard: ip route =="
docker compose exec -T wireguard ip route || true

echo
echo "== spotify_bot: DNS + Yandex API probe =="
docker compose exec -T spotify_bot python - <<'PY'
import socket

import requests

try:
    print("api.music.yandex.net ->", socket.gethostbyname("api.music.yandex.net"))
except Exception as exc:
    print("DNS_ERROR", type(exc).__name__, exc)

try:
    response = requests.get("https://api.music.yandex.net", timeout=10)
    print("YANDEX_HTTP", response.status_code)
    print(response.text[:200])
except Exception as exc:
    print("YANDEX_HTTP_ERROR", type(exc).__name__, exc)
PY
