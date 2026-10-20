"""Create a consistent SQLite backup and prune older copies.

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --keep 30
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import DATABASE_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=14, help="backups to retain")
    args = parser.parse_args()

    if args.keep < 1:
        print("--keep must be at least 1.", file=sys.stderr)
        return 2
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}", file=sys.stderr)
        return 1

    backup_dir = DATABASE_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{DATABASE_PATH.stem}_{stamp}.db"

    source = sqlite3.connect(DATABASE_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    backups = sorted(backup_dir.glob(f"{DATABASE_PATH.stem}_*.db"))
    for old in backups[: -args.keep]:
        old.unlink()

    print(f"Backup written to {target}")
    print(f"Retained {min(len(backups), args.keep)} backup(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
