import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    items = [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
    return items or default


CORS_ORIGINS = env_list(
    "CORS_ORIGINS",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
FRONTEND_DIST = Path(
    os.getenv("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))
)
SERVE_FRONTEND = env_bool("SERVE_FRONTEND", True)
ALLOW_REGISTRATION = env_bool("ALLOW_REGISTRATION", True)
