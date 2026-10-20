# Calorie-Tracker

Full-stack calorie and macro tracker with profile-based daily targets, meal logging, calendar summaries, barcode lookup through Open Food Facts, and an admin food-review workflow.

## Stack

- Frontend: React 19, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy, Alembic, SQLite
- Tests: Pytest, Vitest
- Deployment: FastAPI serves the built frontend on a single origin

## Project Structure

```text
backend/
  app/           API routes, models, services, and seed logic
  migrations/    Alembic migrations
  scripts/       Admin, import, audit, and backup utilities
  tests/         Backend test suite
  data/seed/     Curated food, variant, and serving data
frontend/
  src/app/       Composition root and application shell
  src/features/  Auth, profile, intake, calendar, and admin features
  src/shared/    API client, types, shared UI, styles, and utilities
```

## Local Development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server proxies API requests to the backend.

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run check
```

`npm run check` runs ESLint, Vitest, the TypeScript check, and the production build.

## Production

```powershell
cd frontend
npm ci
npm run check

cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for HTTPS, environment variables, backups, admin bootstrap, and the single-worker SQLite constraint.
