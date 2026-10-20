"""Create an admin user or promote an existing account.

Examples:
    python scripts/manage_user.py promote --username sagar
    python scripts/manage_user.py create --username admin
"""

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import hash_password  # noqa: E402
from app.db import DATABASE_PATH, run_migrations  # noqa: E402


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "promote"])
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    username = args.username.strip().lower()
    if len(username) < 3 or len(username) > 32:
        print("Username must be 3 to 32 characters.", file=sys.stderr)
        return 2

    run_migrations()
    connection = connect(DATABASE_PATH)
    try:
        existing = connection.execute(
            "select id from users where username=?", (username,)
        ).fetchone()
        if args.action == "promote":
            if existing is None:
                print(f"User '{username}' was not found.", file=sys.stderr)
                return 1
            connection.execute(
                "update users set role='admin' where username=?", (username,)
            )
            connection.commit()
            print(f"Promoted '{username}' to admin.")
            return 0

        if existing is not None:
            print(f"User '{username}' already exists.", file=sys.stderr)
            return 1

        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 1
        if len(password) < 8 or len(password) > 128:
            print("Password must be 8 to 128 characters.", file=sys.stderr)
            return 1

        connection.execute(
            """
            insert into users (username, password_hash, role, created_at)
            values (?, ?, 'admin', ?)
            """,
            (
                username,
                hash_password(password),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        print(f"Created admin user '{username}'.")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
