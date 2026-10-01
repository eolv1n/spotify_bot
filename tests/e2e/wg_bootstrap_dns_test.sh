#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$PROJECT_ROOT/deploy/wireguard/init/10-bootstrap-dns.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

test -x "$HOOK"

cat > "$TEST_ROOT/resolvconf" <<'SH'
#!/usr/bin/env sh
set -eu
printf '%s\n' "$*" >> "$WG_TEST_RESOLVCONF_LOG"
if [ "$1" = '-a' ]; then
  cat > "$WG_TEST_RESOLV_CONF"
fi
SH
chmod +x "$TEST_ROOT/resolvconf"

WG_BOOTSTRAP_RESOLVCONF="$TEST_ROOT/resolvconf" \
WG_TEST_RESOLVCONF_LOG="$TEST_ROOT/resolvconf.log" \
WG_TEST_RESOLV_CONF="$TEST_ROOT/resolv.conf" \
  "$HOOK" \
  > "$TEST_ROOT/default.log"

grep -Fxq 'nameserver 127.0.0.11' "$TEST_ROOT/resolv.conf"
grep -Fxq 'options ndots:0' "$TEST_ROOT/resolv.conf"
sed -n '1p' "$TEST_ROOT/resolvconf.log" | grep -Fxq -- '-u'
sed -n '2p' "$TEST_ROOT/resolvconf.log" | grep -Fxq -- '-d wg0 -f'
sed -n '3p' "$TEST_ROOT/resolvconf.log" | grep -Fxq -- '-a eth0.docker'
grep -Fq '[wg-bootstrap] pre-tunnel resolver restored' \
  "$TEST_ROOT/default.log"

WG_BOOTSTRAP_DNS='1.1.1.1' \
WG_BOOTSTRAP_RESOLVCONF="$TEST_ROOT/resolvconf" \
WG_TEST_RESOLVCONF_LOG="$TEST_ROOT/custom-resolvconf.log" \
WG_TEST_RESOLV_CONF="$TEST_ROOT/custom-resolv.conf" \
  "$HOOK" > /dev/null
grep -Fxq 'nameserver 1.1.1.1' "$TEST_ROOT/custom-resolv.conf"

if WG_BOOTSTRAP_DNS='1.1.1.1
nameserver 8.8.8.8' \
  WG_BOOTSTRAP_RESOLVCONF="$TEST_ROOT/resolvconf" \
  WG_TEST_RESOLVCONF_LOG="$TEST_ROOT/rejected.log" \
  WG_TEST_RESOLV_CONF="$TEST_ROOT/rejected.conf" \
  "$HOOK" > /dev/null 2>&1; then
  echo '[FAIL] bootstrap hook accepted an unsafe nameserver value' >&2
  exit 1
fi

grep -Fq \
  './deploy/wireguard/init/10-bootstrap-dns.sh:/custom-cont-init.d/10-bootstrap-dns.sh:ro' \
  "$PROJECT_ROOT/deploy/docker-compose.wireguard.yml"

echo '[OK] WireGuard bootstrap DNS hook is safe and mounted'
