#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

if grep -Eq '\$\{(BOT_ENV_FILE|BOT_CACHE_DIR|WG_CONFIG_DIR):-' \
  "$PROJECT_ROOT/docker-compose.yml"; then
  echo "[FAIL] Production compose still has repo-local runtime defaults" >&2
  exit 1
fi

grep -Fq '${PROD_BOT_ENV_FILE:?' "$PROJECT_ROOT/docker-compose.yml"
grep -Fq '${PROD_BOT_CACHE_DIR:?' "$PROJECT_ROOT/docker-compose.yml"
grep -Fq '${PROD_WG_CONFIG_DIR:?' "$PROJECT_ROOT/docker-compose.yml"
grep -Fq 'export PROD_BOT_ENV_FILE="$BOT_ENV_FILE"' "$PROJECT_ROOT/deploy.sh"
grep -Fq 'export PROD_BOT_CACHE_DIR="$BOT_CACHE_DIR"' "$PROJECT_ROOT/deploy.sh"
grep -Fq 'export PROD_WG_CONFIG_DIR="$WG_CONFIG_DIR"' "$PROJECT_ROOT/deploy.sh"

mkdir -p "$TEST_ROOT/mock-bin"
cat >"$TEST_ROOT/mock-bin/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$DEV_GUARD_ARGS"
MOCK_DOCKER
chmod 0755 "$TEST_ROOT/mock-bin/docker"

DEV_GUARD_ARGS="$TEST_ROOT/default.args" PATH="$TEST_ROOT/mock-bin:$PATH" \
  "$PROJECT_ROOT/scripts/dev.sh"
grep -Fxq -- '-f' "$TEST_ROOT/default.args"
grep -Fxq -- "$PROJECT_ROOT/deploy/docker-compose.dev.yml" "$TEST_ROOT/default.args"
grep -Fxq -- 'up' "$TEST_ROOT/default.args"
grep -Fxq -- '--build' "$TEST_ROOT/default.args"

DEV_GUARD_ARGS="$TEST_ROOT/custom.args" PATH="$TEST_ROOT/mock-bin:$PATH" \
  "$PROJECT_ROOT/scripts/dev.sh" down
grep -Fxq -- 'down' "$TEST_ROOT/custom.args"
if grep -Fxq -- 'up' "$TEST_ROOT/custom.args"; then
  echo "[FAIL] Dev launcher ignored the requested compose command" >&2
  exit 1
fi

echo "[OK] Compose guard regression test passed"
