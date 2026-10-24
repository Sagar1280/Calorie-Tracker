"""Copy an existing SQLite database into an empty PostgreSQL database.

The target schema must already be at the latest Alembic revision. The copy is
performed in one PostgreSQL transaction and row counts are verified before the
transaction is committed.

Usage:
    python scripts/migrate_sqlite_to_postgres.py --target postgresql+psycopg://...
    python scripts/migrate_sqlite_to_postgres.py --dry-run
    python scripts/migrate_sqlite_to_postgres.py --truncate
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Integer, create_engine, func, select, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402,F401
from app.db import DATABASE_PATH, DATABASE_URL, Base  # noqa: E402

TABLES = [table.name for table in Base.metadata.sorted_tables]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"


def to_sync_postgres_url(value: str) -> str:
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("The target must be a PostgreSQL URL.")
    if parsed.drivername in {"postgres", "postgresql", "postgresql+asyncpg"}:
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def schema_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def schema_version(connection) -> str | None:
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def table_rows(source_connection, target_connection, name: str) -> tuple[int, int]:
    table = Base.metadata.tables[name]
    source_count = source_connection.execute(
        select(func.count()).select_from(table)
    ).scalar_one()
    target_count = target_connection.execute(
        select(func.count()).select_from(table)
    ).scalar_one()
    return source_count, target_count


def normalize_row(row, table) -> dict:
    values = {}
    for column in table.columns:
        value = row[column.key]
        if (
            value is not None
            and isinstance(column.type, DateTime)
            and column.type.timezone
            and isinstance(value, datetime)
            and value.tzinfo is None
        ):
            value = value.replace(tzinfo=timezone.utc)
        values[column.key] = value
    return values


def reset_sequences(connection) -> None:
    for name in TABLES:
        table = Base.metadata.tables[name]
        primary_key = list(table.primary_key.columns)
        if len(primary_key) != 1:
            continue
        column = primary_key[0]
        if not isinstance(column.type, Integer):
            continue
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": name, "column_name": column.name},
        ).scalar()
        if not sequence:
            continue
        maximum = connection.execute(select(func.max(column)).select_from(table)).scalar()
        connection.execute(
            text("SELECT setval(:sequence, :value, :is_called)"),
            {
                "sequence": sequence,
                "value": maximum or 1,
                "is_called": maximum is not None,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DATABASE_PATH)
    parser.add_argument("--target", default=DATABASE_URL)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()

    if args.batch_size < 1:
        print("--batch-size must be at least 1.", file=sys.stderr)
        return 2
    if not args.source.exists():
        print(f"Source database not found: {args.source}", file=sys.stderr)
        return 1

    try:
        target_url = to_sync_postgres_url(args.target)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    target_display = make_url(target_url).render_as_string(hide_password=True)
    source_engine = create_engine(f"sqlite:///{args.source.as_posix()}")
    target_engine = create_engine(target_url)

    try:
        with source_engine.connect() as source_connection, target_engine.connect() as target_connection:
            source_version = schema_version(source_connection)
            target_version = schema_version(target_connection)
            expected_version = schema_head()
            if source_version != expected_version:
                print(
                    f"Source schema is at {source_version}, expected {expected_version}. "
                    "Run migrations on the source database first.",
                    file=sys.stderr,
                )
                return 1
            if target_version != expected_version:
                print(
                    f"Target schema is at {target_version}, expected {expected_version}. "
                    "Start the app or run migrations on the target first.",
                    file=sys.stderr,
                )
                return 1

            counts = {}
            for name in TABLES:
                source_count, target_count = table_rows(
                    source_connection, target_connection, name
                )
                counts[name] = source_count
                if target_count and not args.truncate:
                    print(
                        f"Target table '{name}' contains {target_count} row(s). "
                        "Use --truncate only after confirming the target is disposable.",
                        file=sys.stderr,
                    )
                    return 1
                print(f"{name}: {source_count} row(s)")

            if args.dry_run:
                print(f"Dry run complete for {target_display}. No data was written.")
                return 0

        with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
            if args.truncate:
                names = ", ".join(f'"{name}"' for name in reversed(TABLES))
                target_connection.execute(
                    text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")
                )

            for name in TABLES:
                table = Base.metadata.tables[name]
                result = source_connection.execution_options(
                    stream_results=True
                ).execute(select(table))
                batch = []
                for row in result.mappings():
                    batch.append(normalize_row(row, table))
                    if len(batch) >= args.batch_size:
                        target_connection.execute(table.insert(), batch)
                        batch = []
                if batch:
                    target_connection.execute(table.insert(), batch)
                print(f"Copied {counts[name]} row(s) from {name}.")

            for name in TABLES:
                source_count, target_count = table_rows(
                    source_connection, target_connection, name
                )
                if source_count != target_count:
                    raise RuntimeError(
                        f"Row count mismatch for '{name}': "
                        f"source={source_count}, target={target_count}"
                    )

            reset_sequences(target_connection)
            target_connection.execute(text("ANALYZE"))

        print(f"Migration committed to {target_display}.")
        return 0
    except Exception as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
