#!/usr/bin/env sh

set -eu

# wg-quick replaces the container resolver with the DNS server declared in
# wg0.conf. That server is unreachable before wg0 exists and may remain in the
# container-owned resolv.conf after an interrupted stop or host reboot. Restore
# Docker's embedded resolver before linuxserver/wireguard activates tunnels so
# hostname-based endpoints can always bootstrap. wg-quick switches back to the
# configured tunnel DNS after wg0 is up.
bootstrap_dns="${WG_BOOTSTRAP_DNS:-127.0.0.11}"
resolvconf_bin="${WG_BOOTSTRAP_RESOLVCONF:-resolvconf}"

case "$bootstrap_dns" in
  ""|*[!0-9A-Fa-f:.]*)
    echo "[wg-bootstrap] invalid nameserver value" >&2
    exit 1
    ;;
esac

if ! command -v "$resolvconf_bin" >/dev/null 2>&1; then
  echo "[wg-bootstrap] resolvconf is unavailable" >&2
  exit 1
fi

# Regenerate the signed resolv.conf first: direct writes cause openresolv to
# reject wg-quick's later DNS update with "signature mismatch". Remove a stale
# exclusive wg0 record left by an interrupted shutdown, then register Docker's
# embedded DNS as the pre-tunnel fallback. wg-quick adds wg0 as the exclusive
# resolver after the interface is active and removes it on a clean shutdown.
"$resolvconf_bin" -u
"$resolvconf_bin" -d wg0 -f 2>/dev/null || true
printf '%s\n' "nameserver $bootstrap_dns" 'options ndots:0' \
  | "$resolvconf_bin" -a eth0.docker

echo "[wg-bootstrap] pre-tunnel resolver restored"
