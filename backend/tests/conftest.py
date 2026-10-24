import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_TEST_DIR = Path(tempfile.mkdtemp(prefix="calorie-tracker-tests-"))
os.environ["CALORIE_UPLOAD_DIR"] = str(_TEST_DIR / "uploads")
os.environ["ADMIN_CONFIRM_PASSWORD"] = "test-admin-password"

_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if _DATABASE_URL.startswith("postgresql"):
    parsed_url = make_url(_DATABASE_URL)
    if parsed_url.get_backend_name() != "postgresql":
        raise RuntimeError(f"Unsupported test DATABASE_URL: {parsed_url.drivername}")
    if not (parsed_url.database or "").endswith("_test") and os.environ.get(
        "ALLOW_TEST_DB_RESET"
    ) != "1":
        raise RuntimeError(
            "Refusing to reset a non-test PostgreSQL database. "
            "Use a database name ending in '_test' or set ALLOW_TEST_DB_RESET=1."
        )

    os.environ["CALORIE_DB_POOL"] = "null"
    sync_url = parsed_url.set(drivername="postgresql+psycopg")
    reset_engine = create_engine(sync_url)
    with reset_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()
else:
    os.environ.pop("DATABASE_URL", None)
    os.environ["CALORIE_DB_PATH"] = str(_TEST_DIR / "test.db")
