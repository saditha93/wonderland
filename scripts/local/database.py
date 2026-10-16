"""Manage only this project's loopback PostgreSQL cluster; never AWS/system services."""

from pathlib import Path
import argparse
import os
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from scripts.db_migrate import migrate, seed, grant_service_roles, grant_bi_login

DATA = ROOT / "tmp/postgres"
SECRET_DIR = ROOT / "secrets"
CONFIG = SECRET_DIR / "local.env"
PG_BIN = Path("/opt/homebrew/opt/postgresql@17/bin")


def binary(name):
    path = PG_BIN / name
    return str(path) if path.exists() else shutil.which(name) or name


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def secure_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop"])
    args = parser.parse_args()
    if args.action == "stop":
        if (DATA / "postmaster.pid").exists():
            run([binary("pg_ctl"), "-D", str(DATA), "-m", "fast", "stop"])
        else:
            print("Project PostgreSQL is already stopped")
        return
    if not Path(binary("initdb")).exists() and not shutil.which("initdb"):
        raise SystemExit(
            "Install PostgreSQL 17 binaries first (macOS: brew install postgresql@17)"
        )
    SECRET_DIR.mkdir(exist_ok=True, mode=0o700)
    password_file = SECRET_DIR / "native-postgres.password"
    if not password_file.exists():
        secure_write(password_file, secrets.token_urlsafe(36))
    password = password_file.read_text().strip()
    DATA.parent.mkdir(exist_ok=True)
    if not (DATA / "PG_VERSION").exists():
        run(
            [
                binary("initdb"),
                "-D",
                str(DATA),
                "-U",
                "wonderland_owner",
                "-A",
                "scram-sha-256",
                "--pwfile",
                str(password_file),
                "--encoding=UTF8",
                "--locale=C",
            ]
        )
    running = (
        subprocess.run(
            [binary("pg_ctl"), "-D", str(DATA), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if not running:
        socket = ROOT / "tmp/pg-socket"
        socket.mkdir(exist_ok=True, mode=0o700)
        run(
            [
                binary("pg_ctl"),
                "-D",
                str(DATA),
                "-l",
                str(ROOT / "tmp/postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p 55432 -k {socket}",
                "start",
            ]
        )
    base = f"postgresql+psycopg://wonderland_owner:{password}@127.0.0.1:55432/"
    admin = create_engine(base + "postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for name in ["wonderland", "wonderland_test"]:
            if not conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
            ).scalar():
                conn.exec_driver_sql(f"CREATE DATABASE {name}")
    admin.dispose()
    if not CONFIG.exists():
        attr_password = secrets.token_urlsafe(36)
        booking_password = secrets.token_urlsafe(36)
        secure_write(
            CONFIG,
            "\n".join(
                [
                    "APP_ENVIRONMENT=local",
                    "APP_VERSION=0.2.0",
                    "APP_AUTH_MODE=local",
                    f"APP_AUTH_SECRET={secrets.token_urlsafe(48)}",
                    f"APP_TICKET_SECRET={secrets.token_urlsafe(48)}",
                    "APP_PAYMENT_PROVIDER=local",
                    f"APP_LOCAL_WEBHOOK_SECRET={secrets.token_urlsafe(48)}",
                    f"MIGRATION_DATABASE_URL={base}wonderland",
                    f"TEST_DATABASE_URL={base}wonderland_test",
                    f"ATTRACTIONS_DATABASE_URL=postgresql+psycopg://wonderland_attractions:{attr_password}@127.0.0.1:55432/wonderland",
                    f"BOOKING_DATABASE_URL=postgresql+psycopg://wonderland_booking:{booking_password}@127.0.0.1:55432/wonderland",
                    f"LOCAL_ATTRACTIONS_ROLE_PASSWORD={attr_password}",
                    f"LOCAL_BOOKING_ROLE_PASSWORD={booking_password}",
                ]
            )
            + "\n",
        )
    from dotenv import dotenv_values

    values = dotenv_values(CONFIG)
    if values["MIGRATION_DATABASE_URL"] != base + "wonderland":
        raise SystemExit(
            "Existing local.env targets another database; refusing to overwrite it"
        )
    from scripts.local.settings import ensure_config

    ensure_config(CONFIG)
    values = dotenv_values(CONFIG)
    engine = create_engine(values["MIGRATION_DATABASE_URL"])
    migrate(engine)
    seed(engine)
    grant_service_roles(
        engine,
        {
            "attractions": values["LOCAL_ATTRACTIONS_ROLE_PASSWORD"],
            "booking": values["LOCAL_BOOKING_ROLE_PASSWORD"],
            "visits": values["LOCAL_VISITS_ROLE_PASSWORD"],
            "reporting": values["LOCAL_REPORTING_ROLE_PASSWORD"],
        },
    )
    grant_bi_login(engine, values["LOCAL_BI_ROLE_PASSWORD"])
    engine.dispose()
    print(
        "Project PostgreSQL ready on 127.0.0.1:55432; migrations/seeds applied. Secrets saved privately, not printed."
    )
    print("Next: .venv/bin/python scripts/local/services.py")


if __name__ == "__main__":
    main()
