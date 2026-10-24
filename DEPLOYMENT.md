# Deployment

Production runs on one Linux VM with Docker Compose:

```text
Internet :80/:443
  -> Caddy
  -> FastAPI + built frontend   (one Uvicorn worker)
  -> PostgreSQL 17              (private Compose network)
```

Only Caddy publishes a port. PostgreSQL and the app stay on the internal network.
PostgreSQL data, uploaded photos, and Caddy certificates use named volumes.
Caddy terminates HTTPS automatically when `APP_DOMAIN` is a public hostname.

## Prerequisites

- A Linux VM with Docker Engine and the Compose plugin.
- Inbound TCP 22, 80, and 443 open.
- At least 2 GB RAM and 10 GB free disk for a small deployment.
- A GitHub repository with Actions enabled.

## First deployment

Clone the repository on the server and create the environment file:

```bash
sudo mkdir -p /opt/calorie-tracker
sudo chown "$USER":"$USER" /opt/calorie-tracker
git clone https://github.com/YOUR_GITHUB_USERNAME/calorie-tracker.git /opt/calorie-tracker
cd /opt/calorie-tracker
cp .env.production.example .env
chmod 600 .env
```

Generate an alphanumeric database password so it can be embedded in a URL without
escaping:

```bash
openssl rand -hex 24
```

Edit `.env` and set at least:

- `POSTGRES_PASSWORD` and the same password inside `DATABASE_URL`.
- `ADMIN_CONFIRM_PASSWORD` to a separate strong password.
- `APP_DOMAIN` to the DNS hostname pointing at the server.
- `APP_IMAGE`. For the first manual start, `calorie-tracker:local` is simplest.
  CI/CD switches this to the GHCR image later.

Validate and start:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1/api/health
```

The app runs Alembic migrations and seeds default tags on startup. With
`SEED_FOODS_IF_EMPTY=true` (the Compose default), it also imports the curated food
catalog when the foods table is empty. Open `http://SERVER_IP` and create the
first account, then promote it:

```bash
docker compose exec app python /app/backend/scripts/manage_user.py promote --username YOUR_USERNAME
```

After all accounts exist, set `ALLOW_REGISTRATION=false` in `.env` and run
`docker compose up -d` if public sign-up is not wanted.

## Migrating an existing SQLite database

The target PostgreSQL schema must be at the latest Alembic revision and empty
apart from `alembic_version`. The app must not have seeded or written data yet.
In particular, do not run `docker compose up -d app` before the copy: startup
seeds curated foods into an empty database when `SEED_FOODS_IF_EMPTY=true`.

1. Stop the old app and back up the SQLite file:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe scripts\backup_db.py --keep 30
   ```

   Copy the database to the server, for example:

   ```powershell
   scp .\data\calorie_tracker.db USER@SERVER:/opt/calorie-tracker/import/calorie_tracker.db
   ```

2. If the source database is not at the current migration head, upgrade it
   locally before copying:

   ```powershell
   $env:CALORIE_DB_PATH = "C:\path\to\calorie_tracker.db"
   .\.venv\Scripts\alembic.exe upgrade head
   ```

3. On the server, create the schema without starting the app:

   ```bash
   cd /opt/calorie-tracker
   mkdir -p import
   docker compose up -d db
   docker compose run --rm --no-deps app alembic -c /app/backend/alembic.ini upgrade head
   ```

4. Dry-run and then copy:

   ```bash
   docker compose run --rm --no-deps \
     -v "$PWD/import/calorie_tracker.db:/import/old.db:ro" \
     app python /app/backend/scripts/migrate_sqlite_to_postgres.py \
     --source /import/old.db --dry-run

   docker compose run --rm --no-deps \
     -v "$PWD/import/calorie_tracker.db:/import/old.db:ro" \
     app python /app/backend/scripts/migrate_sqlite_to_postgres.py \
     --source /import/old.db
   ```

   The copy runs in one transaction, preserves IDs, treats SQLite timestamps as
   UTC, resets PostgreSQL sequences, and verifies every table's row count before
   committing. It refuses a non-empty target. `--truncate` exists but is only for
   a target you are certain is disposable.

5. Start the app and verify:

   ```bash
   docker compose up -d
   docker compose logs --tail=100 app
   ```

   Log in with an existing account, check foods, entries, reviews, and photo jobs,
   then compare a few row counts:

   ```bash
   docker compose exec db psql -U calorie -d calorie -c \
     "select (select count(*) from foods) foods, (select count(*) from calorie_entries) entries, (select count(*) from users) users;"
   ```

If the target was already seeded, do not use `--truncate` casually. The safest
path is to stop the stack, remove the disposable `pgdata` volume, and repeat from
step 3.

## Local development

SQLite remains the default for local development and for the normal test job:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set `DATABASE_URL` to run against PostgreSQL instead:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://calorie:calorie@127.0.0.1:5432/calorie_test"
.\.venv\Scripts\python.exe -m pytest -q
```

Test databases must end in `_test`; the test setup drops and recreates the
`public` schema. Set `ALLOW_TEST_DB_RESET=1` only if you deliberately want to
reset a differently named disposable database.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_IMAGE` | `calorie-tracker:local` | App image tag used by Compose |
| `POSTGRES_DB` | `calorie` | PostgreSQL database |
| `POSTGRES_USER` | `calorie` | PostgreSQL user |
| `POSTGRES_PASSWORD` | required | PostgreSQL password |
| `DATABASE_URL` | SQLite fallback | App URL, normally `postgresql+asyncpg://...@db:5432/calorie` |
| `ADMIN_CONFIRM_PASSWORD` | required in Compose | Confirms every admin database change |
| `ALLOW_REGISTRATION` | `true` | Public account creation |
| `APP_DOMAIN` | `:80` | Public hostname for Caddy; use a real DNS name for HTTPS |
| `SEED_FOODS_IF_EMPTY` | Compose `true` | Import curated foods when the foods table is empty |
| `COOKIE_SECURE` | `false` | HTTPS-only session cookie and HSTS; set `true` with HTTPS |
| `CORS_ORIGINS` | local Vite origins | Only needed when the frontend is on another origin |
| `DEEPSEEK_API_KEY` | none | Enables photo meal analysis |
| `PHOTO_LLM_BASE_URL` | `https://api.deepseek.com` | Vision API base |
| `PHOTO_LLM_MODEL` | `deepseek-flash` | Vision model ID |
| `PHOTO_LLM_REASONING_EFFORT` | `none` | `none`, `low`, `high`, or `max` |
| `PHOTO_LLM_TIMEOUT_SECONDS` | `60` | Vision request timeout |
| `PHOTO_MAX_IMAGE_BYTES` | `8388608` | Maximum upload size |
| `CALORIE_DB_PATH` | `backend/data/calorie_tracker.db` | SQLite fallback only |

Keep `DATABASE_URL` and `POSTGRES_PASSWORD` in sync. If the password contains
reserved URL characters, percent-encode them (`@` becomes `%40`).

## Single-worker constraint

Keep one Uvicorn worker. PostgreSQL removes SQLite's single-writer limit, but the
request rate limiter, photo-job background tasks, and the day-edit write lock are
still process-local. Horizontal scaling needs a shared limiter, a real job queue,
and a database-backed lock.

## CI/CD

`.github/workflows/ci.yml` runs:

- Backend tests against SQLite.
- Backend tests against PostgreSQL 17.
- Frontend lint, Vitest, TypeScript, and production build.
- A production Docker build.

On pushes to `main` and `v*` tags, the `publish` job pushes images to GHCR with
`sha-<full-sha>`, branch, semver, and `latest` tags.

`.github/workflows/deploy.yml` runs after a successful CI run on `main`. It is
disabled until `DEPLOY_ENABLED` is set.

Configure these repository secrets:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server IP or DNS name |
| `DEPLOY_USER` | SSH user, ideally a dedicated deploy user |
| `DEPLOY_SSH_KEY` | Private key whose public key is in the server's `authorized_keys` |


Configure these repository variables:

| Variable | Value |
| --- | --- |
| `DEPLOY_ENABLED` | `true` only after the server is ready |
| `DEPLOY_PATH` | `/opt/calorie-tracker` |

The deploy job updates the checkout, backs up PostgreSQL when the database is
running, pulls the public `sha-` image from GHCR, starts the stack without
building, and checks `/api/health`.

The first image must exist in GHCR before `DEPLOY_ENABLED=true`, otherwise the
server cannot pull the `sha-` tag. Push to `main` once with deployment disabled,
then enable it.

## Updates and rollback

Normal updates happen through CI/CD. For a manual update:

```bash
cd /opt/calorie-tracker
APP_IMAGE=ghcr.io/OWNER/calorie-tracker:sha-FULL_SHA docker compose pull app
APP_IMAGE=ghcr.io/OWNER/calorie-tracker:sha-FULL_SHA docker compose up -d --no-build
```

Roll back the application by starting a previous `sha-` image tag. Migrations are
forward-only; if a release changed the schema incompatibly, restore the database
backup taken before that release.

## Backups and restore

PostgreSQL backup on the VM:

```bash
cd /opt/calorie-tracker
sh ./deploy/backup_postgres.sh
```

Backups are written to `backups/calorie_YYYYMMDD_HHMMSS.dump`, and the newest 14
are kept. Add a daily cron job:

```cron
0 3 * * * cd /opt/calorie-tracker && sh ./deploy/backup_postgres.sh >> /var/log/calorie-backup.log 2>&1
```

Copy backups off the VM regularly. A backup on the same disk does not survive
disk loss.

Restore, with the app stopped:

```bash
cd /opt/calorie-tracker
docker compose stop app caddy
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < backups/calorie_YYYYMMDD_HHMMSS.dump
docker compose start app caddy
```

The Python helper still supports SQLite:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\backup_db.py --keep 14
```

## HTTPS and camera access

Browsers only allow camera access on HTTPS or `localhost`. Barcode and photo
capture therefore need HTTPS when used from another device.

1. Point a DNS `A` record at the server.
2. Set `APP_DOMAIN` to that hostname in `.env`.
3. Open TCP 80 and 443.
4. Set `COOKIE_SECURE=true` in `.env`.
5. Run `docker compose up -d`; Caddy obtains and renews the certificate.

Caddy obtains and renews the certificate automatically.

## Operations

```bash
docker compose ps
docker compose logs -f --tail=100 app
docker compose logs -f --tail=100 db
docker compose exec db psql -U calorie -d calorie
df -h
docker system df
```

The health endpoint is `GET /api/health`. Logs use Docker's `json-file` driver
with rotation at 10 MB and three files per service.

Check backups by listing them and, periodically, restoring into a disposable
PostgreSQL container. Monitor disk space because PostgreSQL, uploads, images,
and backups all consume it.

## Security checklist

- Keep `.env` mode `600`; never commit it.
- Publish only 22/80 now, plus 443 later. Do not publish PostgreSQL's port.
- Use SSH keys, disable password SSH login, and keep the host patched.
- Set a unique `ADMIN_CONFIRM_PASSWORD`; it is separate from user passwords.
- Set `ALLOW_REGISTRATION=false` after creating accounts.
- Enable `COOKIE_SECURE=true` as soon as HTTPS works.
- The GHCR package is public; do not store secrets in image layers.
- Rotate the deploy key if a laptop or server is lost.
- Test a restore, not just backup creation.
