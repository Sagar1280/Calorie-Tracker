import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = Path(
    os.getenv("CALORIE_DB_PATH", str(DATA_DIR / "calorie_tracker.db"))
)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH.as_posix()}"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

ALEMBIC_INI = BASE_DIR / "alembic.ini"
MIGRATIONS_DIR = BASE_DIR / "migrations"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    connect_args={"timeout": 30},
)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def run_migrations() -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")


async def init_db() -> None:
    await asyncio.to_thread(run_migrations)
