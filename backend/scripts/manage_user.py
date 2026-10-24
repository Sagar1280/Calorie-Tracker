"""Create an admin user or promote an existing account.

Examples:
    python scripts/manage_user.py promote --username sagar
    python scripts/manage_user.py create --username admin
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import hash_password  # noqa: E402
from app.db import SYNC_DATABASE_URL, run_migrations  # noqa: E402
from app.models import User  # noqa: E402


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
    engine = create_engine(SYNC_DATABASE_URL)
    try:
        with Session(engine) as session:
            existing = session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()

            if args.action == "promote":
                if existing is None:
                    print(f"User '{username}' was not found.", file=sys.stderr)
                    return 1
                existing.role = "admin"
                session.commit()
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

            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                )
            )
            session.commit()
            print(f"Created admin user '{username}'.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
