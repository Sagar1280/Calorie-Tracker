import os
from pathlib import Path

from .env import BASE_DIR


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
COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
SEED_FOODS_IF_EMPTY = env_bool("SEED_FOODS_IF_EMPTY", False)
ADMIN_CONFIRM_PASSWORD = os.getenv("ADMIN_CONFIRM_PASSWORD", "").strip()

PHOTO_LLM_API_KEY = os.getenv("PHOTO_LLM_API_KEY") or os.getenv(
    "DEEPSEEK_API_KEY"
)
PHOTO_LLM_BASE_URL = os.getenv(
    "PHOTO_LLM_BASE_URL", "https://api.deepseek.com"
).rstrip("/")
PHOTO_LLM_MODEL = os.getenv("PHOTO_LLM_MODEL", "deepseek-flash")
PHOTO_LLM_REASONING_EFFORT = os.getenv("PHOTO_LLM_REASONING_EFFORT", "none")
PHOTO_LLM_TIMEOUT_SECONDS = float(os.getenv("PHOTO_LLM_TIMEOUT_SECONDS", "60"))
PHOTO_ANALYSIS_ENABLED = bool(PHOTO_LLM_API_KEY)
PHOTO_MAX_IMAGE_BYTES = int(os.getenv("PHOTO_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
PHOTO_UPLOAD_DIR = Path(
    os.getenv("CALORIE_UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
)
PHOTO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
