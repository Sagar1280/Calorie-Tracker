# Deployment

The backend can serve the built frontend directly on one origin, so CORS is not
needed for production.

## Build and run

```powershell
cd "C:\Users\Sagar Work\Desktop\Calorie Tracker\frontend"
npm ci
npm run check

cd "..\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://SERVER_IP:8000`. The frontend is served from `frontend/dist`.

## Single-worker constraint

Run one Uvicorn worker while the app uses SQLite. The day-edit lock and request
rate limiter are process-local. Multiple workers would weaken both, and SQLite
is not a good fit for concurrent writers. Move to PostgreSQL and a shared rate
limit store before scaling horizontally.

## Initial HTTP launch

HTTPS is optional initially, but there are two consequences:

- The session cookie and password travel over plain HTTP. Use this only on a
  trusted local network until HTTPS is configured.
- Browser camera access is blocked on plain HTTP except on `localhost` or
  `127.0.0.1`. The barcode screen detects this and still allows manual entry.
  Camera scanning starts working after HTTPS is added.

Set `COOKIE_SECURE=false` for HTTP and `COOKIE_SECURE=true` after enabling HTTPS.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CALORIE_DB_PATH` | `backend/data/calorie_tracker.db` | SQLite database location |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated dev origins |
| `COOKIE_SECURE` | `false` | Require HTTPS for the session cookie and send HSTS |
| `ALLOW_REGISTRATION` | `true` | Allow public account creation |
| `SERVE_FRONTEND` | `true` | Serve `frontend/dist` from FastAPI |
| `FRONTEND_DIST` | `frontend/dist` | Built frontend directory |
| `OFF_TIMEOUT_SECONDS` | `8` | Open Food Facts request timeout |
| `OFF_CACHE_TTL_SECONDS` | `600` | Positive OFF response cache |
| `OFF_NEGATIVE_CACHE_TTL_SECONDS` | `300` | Missing-product cache |

Example for a same-origin production server:

```powershell
$env:CALORIE_DB_PATH = "D:\Calorie Tracker\calorie_tracker.db"
$env:COOKIE_SECURE = "false"
$env:ALLOW_REGISTRATION = "true"
$env:SERVE_FRONTEND = "true"
$env:FRONTEND_DIST = "C:\Users\Sagar Work\Desktop\Calorie Tracker\frontend\dist"
```

## Admin bootstrap

```powershell
cd "C:\Users\Sagar Work\Desktop\Calorie Tracker\backend"
.\.venv\Scripts\python.exe scripts\manage_user.py promote --username sagar
.\.venv\Scripts\python.exe scripts\manage_user.py create --username admin
```

## Backups

```powershell
.\.venv\Scripts\python.exe scripts\backup_db.py --keep 14
```

Backups are written to `backend/data/backups/`. Run this from Task Scheduler or
another daily job. The SQLite backup API includes committed WAL data.

## Data audit

```powershell
.\.venv\Scripts\python.exe scripts\audit_foods.py
```

This writes `backend/data/qa_report.csv`. The current seed has no high or medium
findings; three low findings are expected fiber/rounding or zero-calorie salt.

## CI

`.github/workflows/ci.yml` runs backend tests plus frontend lint, tests, and the
production build on pushes and pull requests.

## HTTPS later

Put Caddy, nginx, or another TLS reverse proxy in front of port 8000, then set:

```powershell
$env:COOKIE_SECURE = "true"
```

Keep the backend bound to localhost when using a reverse proxy on the same host,
for example `--host 127.0.0.1`. If the proxy does not preserve client addresses,
start Uvicorn with `--proxy-headers --forwarded-allow-ips="127.0.0.1"` so login
rate limiting sees the real client IP. Only trust proxy headers from a known
proxy address.

After HTTPS works, consider setting `ALLOW_REGISTRATION=false` if accounts
should be created only by an administrator.
