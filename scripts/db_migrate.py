"""Versioned local PostgreSQL migrations and repeatable non-destructive seeds."""

from pathlib import Path
import argparse
import os
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = {
    "attractions": ROOT / "services/attractions-service/migrations",
    "booking": ROOT / "services/booking-service/migrations",
}


def migrate(engine):
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(60202026)"))
        for schema, directory in MIGRATIONS.items():
            conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            conn.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {schema}.schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            for path in sorted(directory.glob("*.sql")):
                version = int(path.name.split("_")[0])
                if conn.execute(
                    text(f"SELECT 1 FROM {schema}.schema_migrations WHERE version=:v"),
                    {"v": version},
                ).scalar():
                    continue
                conn.exec_driver_sql(path.read_text())
                conn.execute(
                    text(
                        f"INSERT INTO {schema}.schema_migrations(version) VALUES (:v)"
                    ),
                    {"v": version},
                )


def seed(engine):
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(60202026)"))
        for n, (name, minimum, maximum, cents) in enumerate(
            [
                ("Individual", 1, 1, 4000),
                ("Couple", 2, 2, 7500),
                ("Family", 1, 4, 14000),
                ("Group", 1, 5, 16500),
            ],
            1,
        ):
            conn.execute(
                text("""INSERT INTO booking.ticket_tiers(id,name,min_guests,max_guests,price_cents)
                VALUES (:id,:name,:min,:max,:price) ON CONFLICT DO NOTHING"""),
                {
                    "id": UUID(int=n),
                    "name": name,
                    "min": minimum,
                    "max": maximum,
                    "price": cents,
                },
            )
        for n, row in enumerate(
            [
                (
                    "Skyline Coaster",
                    "Climb above the park before a fast, twisting descent.",
                    "Roller coaster",
                    "high",
                    12,
                    140,
                    "open",
                ),
                (
                    "River Rapids",
                    "A winding water adventure for the whole party.",
                    "Water ride",
                    "moderate",
                    6,
                    110,
                    "open",
                ),
                (
                    "Little Explorers",
                    "Gentle rides and discoveries for younger guests.",
                    "Kids activity",
                    "gentle",
                    0,
                    0,
                    "open",
                ),
                (
                    "Wonder Wheel",
                    "Take in sweeping views from our observation wheel.",
                    "Family ride",
                    "gentle",
                    0,
                    0,
                    "open",
                ),
                (
                    "Moonlight Arcade",
                    "Interactive puzzles and games for curious minds.",
                    "Interactive",
                    "gentle",
                    0,
                    0,
                    "open",
                ),
                (
                    "Thunder Drop",
                    "A thrilling vertical drop, temporarily under maintenance.",
                    "Thrill ride",
                    "high",
                    14,
                    145,
                    "maintenance",
                ),
            ],
            101,
        ):
            name, description, category, thrill, age, height, status = row
            conn.execute(
                text("""INSERT INTO attractions.attractions(id,name,description,category,thrill_level,minimum_age,minimum_height_cm,operational_status)
                VALUES (:id,:name,:description,:category,:thrill,:age,:height,:status) ON CONFLICT DO NOTHING"""),
                {
                    "id": UUID(int=n),
                    "name": name,
                    "description": description,
                    "category": category,
                    "thrill": thrill,
                    "age": age,
                    "height": height,
                    "status": status,
                },
            )


def grant_service_roles(engine, passwords):
    # Identifiers are fixed. Lookup values are bound; generated role secrets are validated before SQL utility commands.
    with engine.begin() as conn:
        for schema, password in passwords.items():
            if schema not in MIGRATIONS:
                raise ValueError("Unknown schema")
            role = f"wonderland_{schema}"
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
            ).scalar()
            if not exists:
                # PostgreSQL utility password clauses cannot be bind parameters.
                # Restrict generated secrets to ASCII URL-safe characters before literal quoting.
                import re

                if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", password):
                    raise ValueError("Invalid generated password")
                try:
                    conn.exec_driver_sql(
                        f"CREATE ROLE {role} LOGIN PASSWORD '{password}'"
                    )
                except SQLAlchemyError:
                    raise RuntimeError(
                        "Service role provisioning failed; credential details suppressed"
                    ) from None
            conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA public FROM {role}")
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
            conn.exec_driver_sql(
                f"GRANT SELECT ON {schema}.schema_migrations TO {role}"
            )
            if schema == "attractions":
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON {schema}.attractions TO {role}"
                )
            else:
                conn.exec_driver_sql(
                    f"GRANT SELECT, UPDATE ON booking.ticket_tiers TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON booking.bookings TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT ON booking.payment_events, booking.outbox TO {role}"
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / "secrets/local.env")
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise SystemExit(
            "Configure local PostgreSQL first; MIGRATION_DATABASE_URL is missing"
        )
    engine = create_engine(url)
    try:
        migrate(engine)
        if args.seed:
            seed(engine)
        passwords = {
            schema: os.environ.get(f"LOCAL_{schema.upper()}_ROLE_PASSWORD")
            for schema in MIGRATIONS
        }
        if all(passwords.values()):
            grant_service_roles(engine, passwords)
        print(
            "Migrations complete"
            + (
                "; repeatable seeds applied without overwriting edits"
                if args.seed
                else ""
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
