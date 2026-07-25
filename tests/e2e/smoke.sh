#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "Checking Python syntax..."
python -m py_compile bot.py app/*.py

echo "Checking application imports with CI-safe credentials..."
CI=true \
TELEGRAM_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" \
SPOTIFY_CLIENT_ID="smoke-client-id" \
SPOTIFY_CLIENT_SECRET="smoke-client-secret" \
python - <<'PY'
import bot

assert callable(bot.main)
assert callable(bot.parse_music_url)
assert callable(bot.search_multisource_tracks)
print("OK: syntax and application imports")
PY
