#!/usr/bin/env bash
set -euo pipefail

# Run on the operator workstation with the shared Baloonz SSH profiles.
REPOSITORY="${REPOSITORY:-eolv1n/spotify_bot}"
EU_HOST="${EU_HOST:-baloonz-foreign}"
SSH_CONFIG="${SSH_CONFIG:-$HOME/.ssh/config}"
WINDOW_UNIT=spotify-actions-ssh-window
SSH_ARGS=(-F "$SSH_CONFIG" -o BatchMode=yes -o ConnectTimeout=10)
ssh_eu() { ssh "${SSH_ARGS[@]}" "$EU_HOST" "$@"; }
cleanup() {
  ssh_eu "ufw --force delete allow proto tcp from 0.0.0.0/0 to any port 22 comment 'spotify-actions-window'; systemctl stop $WINDOW_UNIT.timer; systemctl reset-failed $WINDOW_UNIT.service 2>/dev/null || true" || {
    echo 'Cleanup SSH failed; the pre-installed rollback timer remains responsible for closing the window.' >&2
    return 1
  }
}

gh auth status >/dev/null 2>&1
gh secret list --repo "$REPOSITORY" --json name --jq '.[].name' | grep -Fxq SSH_KEY
HEAD_SHA="$(gh api "repos/$REPOSITORY/commits/main" --jq .sha)"
ssh_eu "test -d /opt/spotify_bot/.git; ufw status | grep -q '^Status: active'; ! systemctl is-active --quiet $WINDOW_UNIT.timer; ! ufw status | grep -Eq '^22/tcp[[:space:]]+ALLOW[[:space:]]+Anywhere'"

# Establish the independent close timer before adding any public rule.
ssh_eu "systemd-run --unit=$WINDOW_UNIT --on-active=20m /usr/sbin/ufw --force delete allow proto tcp from 0.0.0.0/0 to any port 22 comment 'spotify-actions-window'; systemctl is-active --quiet $WINDOW_UNIT.timer"
trap cleanup EXIT
ssh_eu "ufw allow proto tcp from 0.0.0.0/0 to any port 22 comment 'spotify-actions-window'"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh workflow run CI.yml --repo "$REPOSITORY" --ref main -f deploy=true
RUN_ID=''
for attempt in $(seq 1 20); do
  RUN_ID="$(gh run list --repo "$REPOSITORY" --workflow CI.yml --event workflow_dispatch --limit 10 --json databaseId,headSha,createdAt --jq ".[] | select(.headSha == \"$HEAD_SHA\" and .createdAt >= \"$STARTED\") | .databaseId" | head -1)"
  [[ -n "$RUN_ID" ]] && break
  sleep 3
done
[[ -n "$RUN_ID" ]] || { echo 'Dispatched workflow run was not found' >&2; exit 1; }
gh run watch "$RUN_ID" --repo "$REPOSITORY" --exit-status
cleanup
trap - EXIT
ssh_eu "cd /opt/spotify_bot; test \"\$(git rev-parse HEAD)\" = '$HEAD_SHA'; ufw status; ./scripts/prod_smoke.sh"
echo "Deploy verified: $HEAD_SHA (run $RUN_ID)"
