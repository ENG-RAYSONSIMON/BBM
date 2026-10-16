#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${VPS_HOST:?Missing VPS_HOST}"
: "${VPS_USER:?Missing VPS_USER}"
: "${GHCR_USERNAME:?Missing GHCR_USERNAME}"
: "${VPS_SSH_PRIVATE_KEY:?Missing VPS_SSH_PRIVATE_KEY}"
: "${VPS_KNOWN_HOSTS:?Missing VPS_KNOWN_HOSTS}"
: "${GHCR_READ_TOKEN:?Missing GHCR_READ_TOKEN}"
[[ "$VPS_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo "Invalid VPS_HOST (use IPv4 or DNS)." >&2; exit 1; }
[[ "$VPS_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]] || { echo "Invalid VPS_USER." >&2; exit 1; }
[[ "$GHCR_USERNAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]*$ ]] || { echo "Invalid GHCR_USERNAME." >&2; exit 1; }
port="${VPS_PORT:-22}"
[[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] || { echo "Invalid VPS_PORT." >&2; exit 1; }
[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ && "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]] || {
    echo "Invalid GitHub release identifiers." >&2
    exit 1
}

printf '%s\n' "$VPS_SSH_PRIVATE_KEY" > "$RUNNER_TEMP/bbm-ssh-key"
printf '%s\n' "$VPS_KNOWN_HOSTS" > "$RUNNER_TEMP/bbm-known-hosts"
ssh_options=(
    -i "$RUNNER_TEMP/bbm-ssh-key"
    -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes
    -o "UserKnownHostsFile=$RUNNER_TEMP/bbm-known-hosts"
    -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
)
target="$VPS_USER@$VPS_HOST"
release="/opt/apps/bbm/releases/$GITHUB_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
ssh "${ssh_options[@]}" -p "$port" "$target" "umask 077; mkdir -p '$release'; chmod 700 '$release'"
scp "${ssh_options[@]}" -P "$port" \
    "$RUNNER_TEMP/bbm-release/.env" \
    "$RUNNER_TEMP/bbm-release/docker-compose.yml" \
    "$RUNNER_TEMP/bbm-release/deploy.sh" "$target:$release/"
printf '%s' "$GHCR_READ_TOKEN" | ssh "${ssh_options[@]}" -p "$port" "$target" \
    "bash '$release/deploy.sh' '$release' '$GHCR_USERNAME'"
