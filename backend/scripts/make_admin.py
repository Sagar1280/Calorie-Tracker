"""Promote or demote a user account.

Usage:
    python scripts/make_admin.py <username>
    python scripts/make_admin.py <username> --demote
"""

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


async def change_role(username: str, demote: bool) -> int:
    role = "user" if demote else "admin"
    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        if user is None:
            print(f"No user found with username '{username}'.")
            return 1

        user.role = role
        await session.commit()

    print(f"User '{username}' is now {role}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Username to update")
    parser.add_argument(
        "--demote",
        action="store_true",
        help="Set the user back to the regular 'user' role",
    )
    args = parser.parse_args()
    return asyncio.run(change_role(args.username, args.demote))


if __name__ == "__main__":
    raise SystemExit(main())
