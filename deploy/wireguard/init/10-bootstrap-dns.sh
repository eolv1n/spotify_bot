#!/usr/bin/env sh

set -eu

# wg-quick replaces the container resolver with the DNS server declared in
# wg0.conf. That server is unreachable before wg0 exists and may remain in the
# container-owned resolv.conf after an interrupted stop or host reboot. Restore
# Docker's embedded resolver before linuxserver/wireguard activates tunnels so
# hostname-based endpoints can always bootstrap. wg-quick switches back to the
# configured tunnel DNS after wg0 is up.
bootstrap_dns="${WG_BOOTSTRAP_DNS:-127.0.0.11}"
resolv_conf="${WG_BOOTSTRAP_RESOLV_CONF:-/etc/resolv.conf}"

case "$bootstrap_dns" in
  ""|*[!0-9A-Fa-f:.]*)
    echo "[wg-bootstrap] invalid nameserver value" >&2
    exit 1
    ;;
esac

printf '%s\n' \
  '# Pre-tunnel resolver; wg-quick replaces this after wg0 is up.' \
  "nameserver $bootstrap_dns" \
  'options ndots:0' \
  > "$resolv_conf"

echo "[wg-bootstrap] pre-tunnel resolver restored"
