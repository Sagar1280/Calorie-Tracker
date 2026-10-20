from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .admin import router as admin_router
from .auth import COOKIE_SECURE
from .config import CORS_ORIGINS, FRONTEND_DIST, SERVE_FRONTEND
from .db import init_db
from .foods import router as foods_router
from .routers import auth, calories, health, profile, tags
from .seed import seed_default_tags


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    await seed_default_tags()
    yield


app = FastAPI(title="Calorie Tracker API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(self), microphone=(), geolocation=()"
    )
    if COOKIE_SECURE:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(calories.router)
app.include_router(tags.router)
app.include_router(foods_router)
app.include_router(admin_router)


if SERVE_FRONTEND and FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        base = FRONTEND_DIST.resolve()
        candidate = (base / full_path).resolve()
        if base in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(base / "index.html")
