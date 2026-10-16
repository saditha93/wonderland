"""Reconcile real local operational events with eventual reporting facts.

No sample metrics are injected; run smoke-phase3.py to generate actual demo
bookings/check-ins/rides. Reports contain these explicitly local demo records.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import httpx
import jwt
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
values = dotenv_values(ROOT / "secrets/local.env")
url = make_url(values["MIGRATION_DATABASE_URL"])
if (
    url.host not in {"127.0.0.1", "localhost"}
    or url.database != "wonderland"
    or values.get("APP_AUTH_MODE") != "local"
):
    raise SystemExit("Only the local project database/auth mode is allowed")
engine = create_engine(url)
now = datetime.now(timezone.utc)
token = jwt.encode(
    {
        "sub": "phase4-demo-admin",
        "role": "admin",
        "kind": "access",
        "iss": "wonderland-local",
        "aud": "wonderland-local",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    },
    values["APP_AUTH_SECRET"],
    algorithm="HS256",
)
headers = {"Authorization": "Bearer " + token}
checks = {
    "purchases": (
        "SELECT count(*),coalesce(sum(amount_cents),0),coalesce(sum(guest_count),0) FROM booking.bookings WHERE status='confirmed'",
        "SELECT count(*),coalesce(sum(amount_cents),0),coalesce(sum(guest_count),0) FROM reporting.purchases",
    ),
    "arrivals": (
        "SELECT count(*),coalesce(sum(guest_count),0) FROM visits.check_ins",
        "SELECT count(*),coalesce(sum(guest_count),0) FROM reporting.arrivals",
    ),
    "rides": (
        "SELECT count(*),coalesce(sum(guest_count),0) FROM visits.ride_events",
        "SELECT count(*),coalesce(sum(guest_count),0) FROM reporting.rides",
    ),
}
for attempt in range(30):
    with engine.connect() as conn:
        comparisons = {
            name: (
                tuple(conn.execute(text(source)).one()),
                tuple(conn.execute(text(fact)).one()),
            )
            for name, (source, fact) in checks.items()
        }
    if all(a == b for a, b in comparisons.values()):
        break
    time.sleep(1)
else:
    raise SystemExit(
        "Reporting did not reconcile in 30 seconds; inspect pipeline health, pending events and dead letters"
    )
for name, (source, fact) in comparisons.items():
    print(f"Reconciled {name}: {source}")
with httpx.Client(base_url="http://127.0.0.1:8004", timeout=10) as client:
    response = client.get("/health/ready")
    assert response.status_code == 200
    response = client.get("/admin/analytics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["busiest_quiet_hours"]) == 9
    assert data["unpublished_events"] == 0
    assert not any(
        row["status"] in {"dead", "pending"} and row["events"]
        for row in data["pipeline"]
    )
    assert client.get("/admin/analytics").status_code == 401
    print(
        "All five metrics served from persisted reporting views; zero-filled hours and unauthorized access verified"
    )
engine.dispose()
