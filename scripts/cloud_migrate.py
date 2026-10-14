"""Run inside the explicitly approved EKS migration Job; no AWS credentials needed."""

import os
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from scripts.db_migrate import main

if __name__ == "__main__":
    try:
        # Metadata DB is owned separately from the BI/read-only reporting login.
        password = os.environ["LOCAL_METABASE_ROLE_PASSWORD"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", password):
            raise ValueError("Invalid generated password")
        engine = create_engine(
            os.environ["MIGRATION_DATABASE_URL"], isolation_level="AUTOCOMMIT"
        )
        with engine.connect() as conn:
            if not conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname='wonderland_metabase'")
            ).scalar():
                conn.exec_driver_sql(
                    "CREATE ROLE wonderland_metabase LOGIN PASSWORD '" + password + "'"
                )
            conn.exec_driver_sql("GRANT wonderland_metabase TO wonderland_owner")
            if not conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname='wonderland_metadata'")
            ).scalar():
                conn.exec_driver_sql(
                    "CREATE DATABASE wonderland_metadata OWNER wonderland_metabase"
                )
        engine.dispose()
        sys.argv = [sys.argv[0], "--seed"]
        main()
    except Exception:
        raise SystemExit(
            "Cloud migration failed; credential/SQL details suppressed"
        ) from None
