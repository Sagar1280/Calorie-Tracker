# Calorie-Tracker

Full-stack calorie and macro tracker with profile-based daily targets, meal logging, calendar summaries, barcode lookup through Open Food Facts, photo-based meal analysis with DeepSeek, and an admin food-review workflow.

## Stack

- Frontend: React 19, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL in production; SQLite for local development and tests
- Tests: Pytest, Vitest
- Deployment: Docker Compose on one Linux VM, with Caddy and GHCR-based CI/CD

## Project Structure

```text
backend/
  app/           API routes, models, services, and seed logic
  migrations/    Alembic migrations
  scripts/       Admin, import, audit, backup, and SQLite-to-PostgreSQL utilities
  tests/         Backend test suite
  data/seed/     Curated food, variant, and serving data
frontend/
  src/app/       Composition root and application shell
  src/features/  Auth, profile, intake, calendar, and admin features
  src/shared/    API client, types, shared UI, styles, and utilities
deploy/          Server-side operational scripts
```

## Local Development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
Copy-Item .env.example .env
# Add DEEPSEEK_API_KEY and ADMIN_CONFIRM_PASSWORD to .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`backend/.env` is ignored by git and loaded automatically. Keep API keys and
machine-specific paths there. SQLite is the default database; set `DATABASE_URL`
to use PostgreSQL.

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server proxies API requests to the backend.

Camera barcode scanning and photo capture work on `localhost`. Photo analysis
requires `DEEPSEEK_API_KEY` in `backend/.env`. The model defaults to
`deepseek-flash`. Without a key, the Photo mode is shown as unavailable; the rest
of the app works normally.

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run check
```

`npm run check` runs ESLint, Vitest, the TypeScript check, and the production build.

CI also runs the backend suite against PostgreSQL.

## Production

```bash
cp .env.production.example .env
docker compose up -d --build
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for the first deployment, SQLite data
migration, admin bootstrap, HTTPS, backups, restore, and CI/CD setup.

See [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md) for the broader delivery and operations
model.
