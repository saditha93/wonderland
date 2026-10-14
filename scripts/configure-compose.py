"""Generate local-only Compose credentials into an ignored, mode-0600 file."""

from pathlib import Path
import argparse
import os
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.local_phase3 import ensure_config

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("secrets/compose.env"))
args = parser.parse_args()
if args.output.exists():
    ensure_config(args.output)
    print("Compose configuration already exists; preserved without changing passwords.")
    raise SystemExit(0)
args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
owner = secrets.token_urlsafe(36)
attractions = secrets.token_urlsafe(36)
booking = secrets.token_urlsafe(36)
values = {
    "POSTGRES_USER": "wonderland_owner",
    "POSTGRES_DB": "wonderland",
    "POSTGRES_PASSWORD": owner,
    "POSTGRES_HOST_PORT": "5433",
    "APP_ENVIRONMENT": "local",
    "APP_VERSION": "0.2.0",
    "APP_AUTH_MODE": "local",
    "APP_AUTH_SECRET": secrets.token_urlsafe(48),
    "APP_TICKET_SECRET": secrets.token_urlsafe(48),
    "APP_PAYMENT_PROVIDER": "local",
    "APP_LOCAL_WEBHOOK_SECRET": secrets.token_urlsafe(48),
    "LOCAL_ATTRACTIONS_ROLE_PASSWORD": attractions,
    "LOCAL_BOOKING_ROLE_PASSWORD": booking,
    "ATTRACTIONS_DATABASE_URL": f"postgresql+psycopg://wonderland_attractions:{attractions}@postgres:5432/wonderland",
    "BOOKING_DATABASE_URL": f"postgresql+psycopg://wonderland_booking:{booking}@postgres:5432/wonderland",
    "MIGRATION_DATABASE_URL": f"postgresql+psycopg://wonderland_owner:{owner}@postgres:5432/wonderland",
}
fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
ensure_config(args.output)
print(
    "Generated private Compose configuration. Use docker compose --env-file secrets/compose.env; never commit this file."
)
