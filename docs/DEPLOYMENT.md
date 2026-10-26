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
ghcr.io/mlindaamanimwendwa-ictpack/bbm-backend:<full-commit-sha>
ghcr.io/mlindaamanimwendwa-ictpack/bbm-frontend:<full-commit-sha>
```

Use both images from the same successful run. The workflow summary records
digest references; prefer `image@sha256:...` in production. SHA tags identify a
commit but can be overwritten by rerunning a build; digests pin exact content.
Base image tags receive updates, so rebuild deliberately and redeploy by digest.
The examples use the writable fork `mlindaamanimwendwa-ictpack/BBM`; the workflow
derives image names from whichever repository runs it. No `latest` tag is used.
Image publishing runs on pushes to `development` and through manual dispatch.
VPS deployment is disabled until explicitly enabled as described below.
GitHub package visibility is
configured separately; keep packages private unless you intentionally change it.
Pin third-party action/base-image digests under your dependency-update policy.

The frontend build embeds `https://bbmapi.mauzo.tz/api/v1`. Runtime environment
variables cannot change that URL; changing domains also requires updating nginx
hosts, Compose labels and Django origins, then rebuilding.

## Enable GitHub Actions deployment

In **mlindaamanimwendwa-ictpack/BBM**, create an environment named `staging`
under Settings > Environments. Restrict deployment branches to `development`.
Configure required reviewers before enabling deployment, if supported by your
GitHub plan. Declaring an environment in YAML does not create an approval rule.
If required reviewers are unavailable, leave deployment disabled until you are
comfortable with every successful `development` push deploying automatically.

Set these **environment variables** (not secrets):

| Name | Value |
|---|---|
| `VPS_HOST` | VPS IPv4 address or SSH DNS hostname |
| `VPS_PORT` | SSH port, usually `22` |
| `VPS_USER` | Dedicated deployment user |
| `GHCR_USERNAME` | `mlindaamanimwendwa-ictpack` |

Set these **environment secrets**:

| Name | Value |
|---|---|
| `VPS_SSH_PRIVATE_KEY` | Dedicated, noninteractive SSH private key |
| `VPS_KNOWN_HOSTS` | Verified SSH known_hosts entry for the VPS |
| `GHCR_READ_TOKEN` | Token with `read:packages` access to both images |
| `PRODUCTION_ENV` | Completed multiline `deploy/.env.example`, without `BACKEND_IMAGE` or `FRONTEND_IMAGE` |

The workflow also accepts `VPS_HOST`, `VPS_PORT`, `VPS_USER` and `GHCR_USERNAME`
as environment secrets instead of variables; secrets take precedence. Omitting
`VPS_PORT` uses port 22. Thus seven secrets are sufficient when they are
`VPS_HOST`, `VPS_USER`, `GHCR_USERNAME`, `VPS_SSH_PRIVATE_KEY`,
`VPS_KNOWN_HOSTS`, `GHCR_READ_TOKEN` and `PRODUCTION_ENV`.
The environment name `staging` does not isolate infrastructure: this job still
targets `/opt/apps/bbm`, project `bbm`, and the configured public BBM domains.
The repository enable switch retains its name `ENABLE_PRODUCTION_DEPLOY`.

Use a unique Django key of at least 50 characters. Replace every `REPLACE_ME`,
including SMTP credentials and sender. Supply one `NAME=value` assignment per
line, without `export` or inline comments. Single-quote values containing `$`,
`#` or spaces; for example `POSTGRES_PASSWORD='REPLACE_ME'` after filling in the
real value. Do not use double-quoted or multiline values. Percent-encode the
password in DATABASE_URL. Do not change database identifiers/password/URL during
routine updates: initialized PostgreSQL users do not change when `.env` changes.
The deploy script rejects such changes; plan credential rotation separately.

The workflow injects both exact image digests from the successful publishing
matrix. Never put real secrets in Git or Actions artifacts: only the public image
references are uploaded as artifacts. The generated `.env` is mode 600, staged
through SSH, and removed from the runner and remote staging directory afterwards.
Application `.env` and pre-release backup copies persist securely on the VPS.
An interrupted SSH transfer before the remote script starts can leave a staged
`.env` in its mode-700 release directory; inspect and remove it during recovery.
The backend still uses the production Compose file's forced settings module and
volume locations.

On the VPS, create `/opt/apps/bbm` owned by the deployment user, mode 750; install
Docker with Compose v2+, Bash, util-linux (`flock`), and coreutils. Add the key's
public half to that user's `authorized_keys`. Give the user Docker access and
directory write permissions; **Docker access is effectively root access**.
Confirm DNS and `dokploy-network` before enabling releases. No password prompts,
interactive sudo or Docker login prompts may be required.

Obtain the server's SSH host key through a trusted channel (for example the
Contabo console) and verify its fingerprint independently before recording
`VPS_KNOWN_HOSTS`. For a nonstandard SSH port, the entry uses
`[hostname]:port`. Do not trust an unverified `ssh-keyscan` result in the workflow.
IPv6 literals are not supported by the upload helper; use a DNS hostname instead.

Finally, add the **repository variable** `ENABLE_PRODUCTION_DEPLOY=true` under
Settings > Secrets and variables > Actions > Variables. It must be a repository
variable, because the job condition is evaluated before environment variables
are available. Leave it absent or `false` until all configuration and protection
rules are ready. Missing secrets fail the job rather than falling back.

Push the approved changes to `development`. After both images publish, the job
waits for any configured production approval, uploads the production Compose as
`/opt/apps/bbm/docker-compose.yml` plus `.env`, and runs the release. Deployments
are serialized in GitHub and by a VPS file lock. Nothing changes shared Traefik
configuration or deletes volumes.

Images/configuration are validated and pulled before downtime. For an existing
installation, nginx/backend stop while a PostgreSQL dump and both upload stores
are backed up under `/opt/apps/bbm/backups/<release-id>/`, including the previous
configuration. The job then installs the candidate configuration, starts db/redis,
runs migrations and collectstatic, and waits for healthy services.

This is **not zero-downtime**. If backup, migration, collection or readiness fails,
the job fails explicitly and may leave nginx/backend stopped. It does not
automatically roll back migrated data or restart an incompatible old image.
Use the previous configuration/backups and the recovery guidance below to make
an informed recovery. Partial first installs with existing volumes but missing
configuration require manual recovery rather than silently adopting unknown data.
For an existing manual install, first put its actual current Compose at
`/opt/apps/bbm/docker-compose.yml` and preserve its `.env`.

Database/upload backups here are a pre-release safeguard, not a complete backup
service. Encrypt and copy them off-VPS, monitor failures and disk usage, and apply
an explicit retention policy. No automatic deletion or retention job is included.
Registry credentials are temporary for each deployment and removed afterwards.
Creating the first admin user and verifying public TLS/SMTP remain manual tasks.

## Install server-side files

For manual deployment (instead of the Actions job), install `compose.production.yml`
as `docker-compose.yml` and `deploy/.env.example` as `.env.example` from the same
reviewed release. A source checkout is unnecessary. On the VPS:

```bash
sudo install -d -m 750 /opt/apps/bbm
# Copy the production Compose as docker-compose.yml and the example as .env.example.
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
docker compose config --quiet
docker compose pull
docker compose up -d --wait db redis
docker compose run --rm backend python manage.py check --deploy
docker compose run --rm backend python manage.py migrate --noinput
docker compose run --rm backend python manage.py collectstatic --noinput
docker compose up -d --wait
docker compose exec backend python manage.py createsuperuser
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
docker compose stop nginx backend
umask 077
mkdir -p backups
docker compose exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/database.dump
docker compose run --rm --no-deps -T backend \
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
docker compose up -d --wait db redis
docker compose exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --no-owner' \
  < backups/database.dump
docker compose run --rm --no-deps -T backend \
  tar -C /app -xzf - < backups/uploads.tar.gz
docker compose run --rm backend python manage.py collectstatic --noinput
docker compose up -d --wait
```

Restore only trusted archives. The tar archive preserves UID 10001 ownership;
importing another deployment's uploads may require an explicit ownership fix.
Do not run pg_restore against a populated live database using these commands.
Verify receipt authorization, row counts and images after restoration. Never use
`docker compose down -v` for routine updates; it destroys application data.

## Scheduled jobs

The `scheduler` service runs the backend image with
`python manage.py generate_notifications` once an hour (FR-19 low-stock and
expiry alerts). It has no ports and no healthcheck: the loop keeps running even
if a run fails, so check its logs (`docker compose logs --tail=50 scheduler`) for
`Notifications: … opened` lines or errors. The command is idempotent, so a run
right after a restart or a manual run is harmless:

```bash
docker compose exec scheduler python manage.py generate_notifications
```

`deploy.sh` stops only nginx and backend before the backup. The scheduler keeps
running through `pg_dump` (a consistent snapshot) and `migrate`, and it is
recreated with the new image by the final `up -d`. It only writes notification
rows, which the next run rebuilds. Once every server has a release with the
scheduler service, `deploy.sh` can also stop it before the backup.

## Checks before accepting a release

```bash
docker compose ps
docker compose logs --tail=100 backend nginx scheduler
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
