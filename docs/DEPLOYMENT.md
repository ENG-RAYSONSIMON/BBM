# Contabo deployment: GHCR, Compose and existing Dokploy Traefik

This is a **standalone Docker Compose** application, not a Swarm stack. Keep
development on `docker-compose.yml`; deploy with `compose.production.yml`.
Only nginx joins the existing `dokploy-network`. No application service publishes
host ports. Traefik owns TLS; BBM must not change Dokploy's shared configuration.

| Host | Destination |
|---|---|
| `bbm.mauzo.tz` | Built React frontend, including SPA deep links |
| `bbmapi.mauzo.tz/api/v1/` | Django API |
| `bbmapi.mauzo.tz/admin/` | Django admin |
| `bbmapi.mauzo.tz/static/` | Collected Django/admin assets |
| `bbmapi.mauzo.tz/media/` | Public product images |

Expense receipts are **not public**. Their separate `private_media` volume is
mounted only by Django; existing tenant/permission checks authorize downloads.
Nginx reads public media and static volumes read-only. Backend runs as UID/GID
10001; both images give shared mountpoints that same ownership, so Docker
initializes fresh named volumes correctly regardless of container creation order.
If importing files, set directory ownership to 10001:10001; public directories
need mode 755 and public files 644 so nginx can read them. Never use chmod 777.

## Before deployment

- Confirm the VPS is amd64 (the default GitHub runner builds amd64 images).
  For an ARM VPS, add Buildx/QEMU and an explicit matching platform before publishing.
- Both DNS records must resolve to the VPS. Check AAAA records too. Ports 80/443
  must reach existing Traefik; its `websecure` entrypoint and `letsencrypt`
  resolver are used by the supplied labels.
- Verify `docker network inspect dokploy-network` and that Traefik's Docker
  provider can discover standalone containers. Do not create a replacement proxy.
- Reserve the `bbm` project name and `bbm-*` Traefik router/middleware names.
  The application network must not contain untrusted containers. The shared
  Dokploy network is also a trust boundary: its other workloads must be trusted,
  since they can connect to nginx and supply forwarding headers.
- Do not enable insecure forwarded-header trust on Traefik. It must sanitize
  client-supplied forwarding headers. Django expects two hops: Traefik and nginx.
- Inspect the existing proxy's published ports/firewall: `api.insecure: true`
  enables a dashboard/API listener but does not establish whether it is public.
  Restrict it if exposed, with the Dokploy administrator's approval.
- Replace Traefik's `test@localhost.com` ACME contact with a monitored address
  through your normal Dokploy administration process. Preserve `acme.json`.
- Determine whether this is a fresh database or a migration of existing data.
  Never initialize a fresh volume and assume it contains development data.

## Publish images

Push the reviewed commit to `development` to run **Publish production images**,
or run it manually in GitHub Actions once the workflow exists on the default
branch. Backend checks gate publishing; frontend checks run
before its image build. Images are:

```text
ghcr.io/eng-raysonsimon/bbm-backend:<full-commit-sha>
ghcr.io/eng-raysonsimon/bbm-frontend:<full-commit-sha>
```

Use both images from the same successful run. The workflow summary records
digest references; prefer `image@sha256:...` in production. SHA tags identify a
commit but can be overwritten by rerunning a build; digests pin exact content.
Base image tags receive updates, so rebuild deliberately and redeploy by digest.
No automatic VPS deployment or `latest` tag is used. Image publishing runs on
pushes to `development` and through manual dispatch. GitHub package visibility is
configured separately; keep packages private unless you intentionally change it.
Pin third-party action/base-image digests under your dependency-update policy.

The frontend build embeds `https://bbmapi.mauzo.tz/api/v1`. Runtime environment
variables cannot change that URL; changing domains also requires updating nginx
hosts, Compose labels and Django origins, then rebuilding.

## Install server-side files

Install only `compose.production.yml` and `deploy/.env.example` from the same
reviewed release. A source checkout is unnecessary. On the VPS:

```bash
sudo install -d -m 750 /opt/apps/bbm
# Copy compose.production.yml and the example here using your normal transfer tool.
cd /opt/apps/bbm
cp .env.example .env
chmod 600 .env
```

Fill every `REPLACE_ME`. Generate a unique Django key of at least 50 characters
and a strong database password. Percent-encode special characters in the
DATABASE_URL password, keeping POSTGRES_PASSWORD unencoded. Quote dotenv values
containing `$` with single quotes to avoid Compose interpolation. The `.env`
contains all backend configuration, including SMTP credentials; keep it off Git,
out of images, and out of logs. Configure a real SMTP sender and verify delivery.
The production settings module ignores DEBUG=True and requires Redis.

For private GHCR packages, authenticate using a read-only package token:

```bash
read -rsp 'GHCR read:packages token: ' GHCR_TOKEN; echo
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
unset GHCR_TOKEN
```

Docker credentials persist on the server; protect the Docker configuration or use
a credential helper. GHCR workflow tokens are not long-lived VPS credentials.

## Initial release

Run from `/opt/apps/bbm`. Project name `bbm` fixes volume names; do not change it.
Do not print resolved Compose configuration containing secrets into shared logs.

```bash
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml pull
docker compose -f compose.production.yml up -d --wait db redis
docker compose -f compose.production.yml run --rm backend python manage.py check --deploy
docker compose -f compose.production.yml run --rm backend python manage.py migrate --noinput
docker compose -f compose.production.yml run --rm backend python manage.py collectstatic --noinput
docker compose -f compose.production.yml up -d --wait
docker compose -f compose.production.yml exec backend python manage.py createsuperuser
```

Security checks may warn about intentionally omitted HSTS subdomains/preload.
Enable neither blindly on a domain with unrelated applications. Migration and
static failures must stop the release; never start nginx before they succeed.
Empty named volumes are populated with UID/GID 10001 ownership from either image.
Do not substitute images with differently owned shared mountpoints.

## Updates and rollback

Record the currently deployed image digests and keep the previous `.env` securely.
For this single-VPS procedure, schedule a maintenance window: stop nginx/backend,
leaving db/redis running, then take a consistent backup as below. Update both image
references, pull, run checks/migrations/collectstatic, then `up -d --wait` using the
same commands as the initial release. Never run migrations in every worker startup.

Do not use `collectstatic --clear` during normal updates; retained assets help old
pages and rollback. Django's current static storage uses stable names, so this
procedure is not zero-downtime: a new Django release may overwrite admin assets.
On application rollback, restore both previous image digests and run collectstatic
from the previous backend before restarting. Review database compatibility first:
switching images does not reverse schema/data migrations. Prefer a forward fix.
If restoring a database backup is necessary, restore matching uploaded files too
and acknowledge that writes since the backup will be lost.

## Backups and recovery

Back up PostgreSQL, `bbm_media`, `bbm_private_media`, the release Compose and the
protected configuration. Redis counters and rebuildable static files are not
business records. A persistent volume on the same VPS is not a backup.

During the maintenance window, stop all BBM writers:

```bash
docker compose -f compose.production.yml stop nginx backend
umask 077
mkdir -p backups
docker compose -f compose.production.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/database.dump
docker compose -f compose.production.yml run --rm --no-deps -T backend \
  tar -C /app -czf - media private_media > backups/uploads.tar.gz
```

Check command exit statuses and nonempty output before accepting a backup.
Use a fresh date/versioned directory per backup rather than overwriting the last
good copy. Encrypt and copy backups off the VPS; set a retention policy based on
your acceptable data-loss window, monitor backup failures, and rehearse recovery
in an isolated environment. Never keep unencrypted receipt backups in a public
web directory. Restart only after the backup or release procedure succeeds.

For recovery to an **empty isolated deployment** with matching project/network
configuration and images:

```bash
docker compose -f compose.production.yml up -d --wait db redis
docker compose -f compose.production.yml exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --no-owner' \
  < backups/database.dump
docker compose -f compose.production.yml run --rm --no-deps -T backend \
  tar -C /app -xzf - < backups/uploads.tar.gz
docker compose -f compose.production.yml run --rm backend python manage.py collectstatic --noinput
docker compose -f compose.production.yml up -d --wait
```

Restore only trusted archives. The tar archive preserves UID 10001 ownership;
importing another deployment's uploads may require an explicit ownership fix.
Do not run pg_restore against a populated live database using these commands.
Verify receipt authorization, row counts and images after restoration. Never use
`docker compose down -v` for routine updates; it destroys application data.

## Checks before accepting a release

```bash
docker compose -f compose.production.yml ps
docker compose -f compose.production.yml logs --tail=100 backend nginx
curl -I http://bbm.mauzo.tz
curl -I https://bbm.mauzo.tz
curl -I https://bbmapi.mauzo.tz/admin/login/
```

Confirm HTTP redirects to HTTPS and certificates are valid for both domains.
Load a frontend deep link directly, register/login, switch languages, upload a
product image, and verify it is an HTTPS URL on the API domain. Exercise a 5 MiB
receipt upload (nginx allows 6 MiB for multipart overhead). Download the receipt
with the owning user; another tenant and unauthenticated requests must fail.
Neither domain may expose `/private_media/`; API 404s must not return the SPA.
Recreate backend/nginx and confirm uploaded files persist.

Verify CORS allows only the frontend origin and admin CSRF works at the API
domain. Confirm rate limits distinguish separate clients and cannot be bypassed
with forged X-Forwarded-For headers through Traefik. Avoid logging authorization
headers, SMTP credentials or reset-token query strings. Gunicorn access logs omit
query strings; nginx does not proxy-log private reset queries on the frontend.

Container healthchecks report HTTP readiness but do not auto-restart unhealthy
processes; restart policies restart exited processes. Monitor external HTTPS,
database connectivity, container health/restarts, disk usage, volume growth,
backup age/failures and certificate renewal. Docker JSON logs rotate at 3 x 10 MiB
per service. Budget memory and tune Gunicorn workers based on measured VPS load.
Schedule `manage.py flushexpiredtokens` periodically to prune expired JWT records;
do not introduce Celery solely for this deployment.
