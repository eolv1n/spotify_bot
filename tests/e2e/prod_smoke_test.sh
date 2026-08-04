#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/mock-bin"
cat >"$TEST_ROOT/mock-bin/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  inspect)
    if [[ "$*" == *'Health.Status'* ]]; then
      echo healthy
    else
      echo true
    fi
    ;;
  logs)
    echo 'INFO Бот запущен и готов к работе (включая inline-режим)'
    ;;
  exec)
    if [[ "$*" == *'python -'* ]]; then
      cat >/dev/null
      printf '%s\n' \
        telegram_get_me=ok \
        spotify_token=ok \
        yandex_https=ok \
        sqlite_quick_check=ok
    elif [[ "$*" == *'latest-handshakes'* ]]; then
      echo 'public-key 1785840000'
    fi
    ;;
  *)
    echo "unexpected docker command: $*" >&2
    exit 2
    ;;
esac
MOCK_DOCKER
chmod 0755 "$TEST_ROOT/mock-bin/docker"

PATH="$TEST_ROOT/mock-bin:$PATH" \
SMOKE_ATTEMPTS=1 \
  "$PROJECT_ROOT/scripts/prod_smoke.sh" >/dev/null

cat >"$TEST_ROOT/mock-bin/docker" <<'MOCK_FAILURE'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == inspect ]]; then
  echo false
else
  exit 1
fi
MOCK_FAILURE
chmod 0755 "$TEST_ROOT/mock-bin/docker"

if PATH="$TEST_ROOT/mock-bin:$PATH" SMOKE_ATTEMPTS=1 \
  "$PROJECT_ROOT/scripts/prod_smoke.sh" >/dev/null 2>&1; then
  echo "[FAIL] Production smoke accepted a stopped runtime" >&2
  exit 1
fi

grep -q './scripts/prod_smoke.sh' "$PROJECT_ROOT/deploy.sh"
grep -q 'rollback_bot_image' "$PROJECT_ROOT/deploy.sh"
if grep -q 'f"{url} returned' "$PROJECT_ROOT/scripts/prod_smoke.sh"; then
  echo "[FAIL] Production smoke can expose a secret-bearing URL" >&2
  exit 1
fi

echo "[OK] Production smoke regression test passed"
