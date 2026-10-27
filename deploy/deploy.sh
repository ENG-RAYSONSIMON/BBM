#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app=/opt/apps/bbm
release="${1:?Release directory required}"
username="${2:?GHCR username required}"
[[ "$release" =~ ^/opt/apps/bbm/releases/[0-9a-f]{40}-[0-9]+-[0-9]+$ ]] || { echo "Invalid release directory." >&2; exit 1; }
[[ "$username" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]*$ ]] || { echo "Invalid GHCR username." >&2; exit 1; }
chmod 600 "$release/.env"

export DOCKER_CONFIG="$release/docker-auth"
mkdir -m 700 "$DOCKER_CONFIG"
cleanup() {
    rm -f "$DOCKER_CONFIG/config.json"
    rmdir "$DOCKER_CONFIG"
    rm -f "$release/.env"
}
trap cleanup EXIT
failed() {
    echo "Deployment failed. Review $release and $app/backups before recovery; no database rollback was attempted." >&2
}
trap failed ERR
# A host lock also excludes releases launched outside GitHub Actions.
exec 9>"$app/.deploy.lock"
flock -n 9 || { echo "Another BBM deployment holds the VPS lock." >&2; exit 1; }
docker login ghcr.io --username "$username" --password-stdin
docker network inspect dokploy-network >/dev/null

candidate() {
    docker compose -p bbm --env-file "$release/.env" -f "$release/docker-compose.yml" "$@"
}
current() {
    docker compose -p bbm --env-file "$app/.env" -f "$app/docker-compose.yml" "$@"
}

candidate config --quiet
candidate pull

backup="$app/backups/$(basename "$release")"
mkdir -p "$backup"
chmod 700 "$app/backups" "$backup"
existing=false
if [[ -f "$app/docker-compose.yml" || -f "$app/.env" ]]; then
    test -f "$app/docker-compose.yml" && test -f "$app/.env"
    existing=true
    # A changed database URL/password is a manual migration, not a routine release.
    for key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD DATABASE_URL; do
        old="$(grep "^$key=" "$app/.env")"
        new="$(grep "^$key=" "$release/.env")"
        if [[ "$old" != "$new" ]]; then
            echo "Refusing automatic change to $key; migrate database credentials manually." >&2
            exit 1
        fi
    done
else
    # Refuse to adopt unknown data on a nominal first install.
    for volume in bbm_pgdata bbm_media bbm_private_media; do
        if docker volume inspect "$volume" >/dev/null 2>&1; then
            echo "Existing $volume without installed configuration; manual recovery required." >&2
            exit 1
        fi
    done
fi

candidate run --rm --no-deps -T backend python manage.py check --deploy
if [[ "$existing" == true ]]; then
    cp "$app/docker-compose.yml" "$backup/docker-compose.yml"
    cp "$app/.env" "$backup/.env"
    chmod 600 "$backup/.env"
    current up -d --wait --wait-timeout 120 db redis
    current stop nginx backend
    # Credentials expand inside the container, not on the SSH host.
    # shellcheck disable=SC2016
    current exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/database.dump"
    current run --rm --no-deps -T backend tar -C /app -czf - media private_media > "$backup/uploads.tar.gz"
    test -s "$backup/database.dump"
    test -s "$backup/uploads.tar.gz"
fi

install -m 600 "$release/.env" "$app/.env"
install -m 644 "$release/docker-compose.yml" "$app/docker-compose.yml"
current up -d --wait --wait-timeout 120 db redis
current run --rm -T backend python manage.py migrate --noinput
current run --rm -T backend python manage.py collectstatic --noinput
# The scheduler isn't waited for: a failing job (shown as unhealthy in ps
# below) must not fail a release whose migrations already ran.
current up -d scheduler
current up -d --wait --wait-timeout 180 db redis backend nginx
current ps
echo "BBM deployment completed. Verify public HTTPS and real SMTP delivery."
