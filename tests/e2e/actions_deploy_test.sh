#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir -p "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/ssh" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$WINDOW_TEST_LOG"
if [[ "$*" == *'systemd-run'* && "${WINDOW_TEST_FAIL_TIMER:-0}" == 1 ]]; then
  exit 1
fi
MOCK
cat > "$TEST_ROOT/bin/gh" <<'MOCK'
#!/usr/bin/env bash
printf 'gh %s\n' "$*" >> "$WINDOW_TEST_LOG"
case "$1 $2" in
  'secret list') echo SSH_KEY ;;
  'api repos/'*) echo 0123456789abcdef ;;
  'run list') echo 123456 ;;
  'run watch') exit "${WINDOW_TEST_FAIL_RUN:-0}" ;;
esac
MOCK
chmod +x "$TEST_ROOT/bin/ssh" "$TEST_ROOT/bin/gh"
export PATH="$TEST_ROOT/bin:$PATH"
export WINDOW_TEST_LOG="$TEST_ROOT/commands"
bash "$PROJECT_ROOT/scripts/actions_deploy.sh" > /dev/null
timer_line="$(grep -n systemd-run "$WINDOW_TEST_LOG" | cut -d: -f1)"
open_line="$(grep -n 'ufw allow proto' "$WINDOW_TEST_LOG" | cut -d: -f1)"
close_line="$(grep -n 'ufw --force delete' "$WINDOW_TEST_LOG" | tail -1 | cut -d: -f1)"
[[ "$timer_line" -lt "$open_line" && "$open_line" -lt "$close_line" ]]

: > "$WINDOW_TEST_LOG"
if WINDOW_TEST_FAIL_TIMER=1 bash "$PROJECT_ROOT/scripts/actions_deploy.sh" > /dev/null 2>&1; then
  echo '[FAIL] Failed timer allowed deployment' >&2
  exit 1
fi
if grep -q 'ufw allow proto' "$WINDOW_TEST_LOG"; then
  echo '[FAIL] Public SSH opened before a working close timer' >&2
  exit 1
fi

: > "$WINDOW_TEST_LOG"
if WINDOW_TEST_FAIL_RUN=1 bash "$PROJECT_ROOT/scripts/actions_deploy.sh" > /dev/null 2>&1; then
  echo '[FAIL] Failed workflow accepted' >&2
  exit 1
fi
grep -q 'ufw --force delete' "$WINDOW_TEST_LOG"
echo '[OK] SSH window ordering and failure cleanup passed'
