"""Create a consistent database backup and prune older copies.

SQLite uses the sqlite3 backup API. PostgreSQL shells out to pg_dump, so the
client tools must be installed (or use deploy/backup_postgres.sh on the VM).

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --keep 30
"""

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import DATA_DIR, DATABASE_PATH, DATABASE_URL, IS_SQLITE  # noqa: E402


def backup_sqlite(backup_dir: Path, keep: int, stamp: str) -> int:
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}", file=sys.stderr)
        return 1

    target = backup_dir / f"{DATABASE_PATH.stem}_{stamp}.db"
    source = sqlite3.connect(DATABASE_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    backups = sorted(backup_dir.glob(f"{DATABASE_PATH.stem}_*.db"))
    for old in backups[: -keep]:
        old.unlink()

    print(f"Backup written to {target}")
    print(f"Retained {min(len(backups), keep)} backup(s).")
    return 0


def backup_postgres(backup_dir: Path, keep: int, stamp: str) -> int:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        print(
            "pg_dump was not found. On the Docker deployment run "
            "deploy/backup_postgres.sh from the project root instead.",
            file=sys.stderr,
        )
        return 1

    url = make_url(DATABASE_URL)
    target = backup_dir / f"calorie_{stamp}.dump"
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    sslmode = url.query.get("sslmode") or url.query.get("ssl")
    if isinstance(sslmode, tuple):
        sslmode = sslmode[-1]
    if sslmode and str(sslmode).lower() not in {"true", "false"}:
        environment["PGSSLMODE"] = str(sslmode)

    command = [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(target),
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 5432),
        "--username",
        url.username or "postgres",
        "--dbname",
        url.database or "postgres",
    ]
    subprocess.run(command, env=environment, check=True)

    backups = sorted(backup_dir.glob("calorie_*.dump"))
    for old in backups[: -keep]:
        old.unlink()

    print(f"Backup written to {target}")
    print(f"Retained {min(len(backups), keep)} backup(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=14, help="backups to retain")
    args = parser.parse_args()

    if args.keep < 1:
        print("--keep must be at least 1.", file=sys.stderr)
        return 2

    backup_dir = (DATABASE_PATH.parent if IS_SQLITE else DATA_DIR) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if IS_SQLITE:
        return backup_sqlite(backup_dir, args.keep, stamp)
    return backup_postgres(backup_dir, args.keep, stamp)


if __name__ == "__main__":
    raise SystemExit(main())
