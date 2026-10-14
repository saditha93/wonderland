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
    "reporting": ROOT / "services/analytics-worker/migrations",
    "attractions": ROOT / "services/attractions-service/migrations",
    "booking": ROOT / "services/booking-service/migrations",
    "visits": ROOT / "services/gate-ride-service/migrations",
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
            elif schema == "booking":
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON booking.ticket_tiers TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON booking.bookings TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT ON booking.payment_events, booking.outbox TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON booking.visitor_profiles TO {role}"
                )
            elif schema == "visits":
                conn.exec_driver_sql(
                    f"GRANT SELECT, INSERT ON visits.check_ins,visits.ride_events,visits.outbox TO {role}"
                )

            elif schema == "reporting":
                conn.exec_driver_sql(
                    f"REVOKE INSERT, UPDATE ON ALL TABLES IN SCHEMA reporting FROM {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO {role}"
                )
                conn.exec_driver_sql(
                    f"GRANT INSERT ON reporting.queue,reporting.processed_events,reporting.purchases,reporting.arrivals,reporting.rides TO {role}"
                )
                conn.exec_driver_sql(f"GRANT UPDATE ON reporting.queue TO {role}")
                for source in ("booking", "visits"):
                    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {source} TO {role}")
                    conn.exec_driver_sql(
                        f"REVOKE UPDATE ON {source}.outbox FROM {role}"
                    )
                    conn.exec_driver_sql(
                        f"GRANT SELECT, UPDATE(published_at) ON {source}.outbox TO {role}"
                    )
        # Fixed read-only BI role; no operational schema access or queue access.
        if "reporting" in passwords:
            conn.exec_driver_sql(
                "DO $$ BEGIN CREATE ROLE wonderland_bi NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
            conn.exec_driver_sql("GRANT USAGE ON SCHEMA reporting TO wonderland_bi")
            views = (
                "daily_arrivals",
                "tickets_by_tier",
                "revenue_by_tier",
                "popular_attractions",
                "arrival_hours",
                "busiest_quiet_hours",
                "outside_hours_arrivals",
            )
            for view in views:
                conn.exec_driver_sql(
                    f"GRANT SELECT ON reporting.{view} TO wonderland_bi"
                )


def grant_bi_login(engine, password):
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", password):
        raise ValueError("Invalid generated BI password")
    with engine.begin() as conn:
        # Provision once; repeated runs preserve the original password.
        login = conn.execute(
            text("SELECT rolcanlogin FROM pg_roles WHERE rolname='wonderland_bi'")
        ).scalar()
        if login is False:
            try:
                conn.exec_driver_sql(
                    f"ALTER ROLE wonderland_bi LOGIN PASSWORD '{password}'"
                )
            except SQLAlchemyError:
                raise RuntimeError(
                    "BI login provisioning failed; credentials suppressed"
                ) from None
        conn.exec_driver_sql(
            "ALTER ROLE wonderland_bi SET default_transaction_read_only=on"
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
        if os.environ.get("LOCAL_BI_ROLE_PASSWORD"):
            grant_bi_login(engine, os.environ["LOCAL_BI_ROLE_PASSWORD"])
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
