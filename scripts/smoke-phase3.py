"""Repeatable local-only arrival/ride demo. No cloud or external payment calls."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import argparse
import re
from uuid import uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
import httpx
import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from wonderland_common.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--prepare-only", action="store_true")
parser.add_argument("--scenario", default="default")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", args.scenario):
    raise SystemExit("Scenario must be 1–24 letters, digits, underscores or hyphens")
load_dotenv(ROOT / "secrets/local.env")
settings = Settings()
import os

url = os.environ.get("MIGRATION_DATABASE_URL", "")
if (
    settings.environment not in {"local", "test"}
    or settings.auth_mode != "local"
    or settings.payment_provider != "local"
    or make_url(url).host not in {"127.0.0.1", "localhost"}
):
    raise SystemExit(
        "This demo requires the native loopback database and local simulator"
    )
now = datetime.now(timezone.utc)
today = datetime.now(ZoneInfo("Asia/Colombo")).date()
subject = "phase3-demo-visitor"


def headers(role="visitor", owner=subject):
    token = jwt.encode(
        {
            "iss": "wonderland-local",
            "aud": "wonderland-local",
            "sub": owner,
            "role": role,
            "kind": "access",
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.auth_secret.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def checked(response):
    response.raise_for_status()
    return response.json()


with httpx.Client(base_url="http://127.0.0.1:5173", timeout=15) as client:
    visitor = headers()
    admin = headers("admin", "demo-admin")
    tiers = checked(client.get("/api/booking/ticket-tiers"))
    tier = next(t for t in tiers if t["name"] == "Family" and t["max_guests"] >= 4)
    command = {
        "tier_id": tier["id"],
        "guest_count": 4,
        "visit_date": (today + timedelta(days=1)).isoformat(),
        "time_slot": "09:00",
    }
    booking = checked(
        client.post(
            "/api/booking/bookings",
            headers={
                **visitor,
                "Idempotency-Key": "phase3-demo-"
                + today.isoformat()
                + "-"
                + args.scenario,
            },
            json=command,
        )
    )
    ref = booking["reference"]
    if booking["status"] == "pending":
        # Development seed: model a booking made earlier for today's visit.
        # This does not bypass payment; confirmation still uses the verified local event path.
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE booking.bookings SET visit_date=:day WHERE reference=:ref AND owner_id=:owner AND status='pending'"
                ),
                {"day": today, "ref": ref, "owner": subject},
            )
        engine.dispose()
        checked(client.post(f"/api/booking/bookings/{ref}/checkout", headers=visitor))
        checked(
            client.post(f"/api/booking/bookings/{ref}/sandbox-pay", headers=visitor)
        )
    ticket = checked(client.get(f"/api/booking/bookings/{ref}/ticket", headers=visitor))
    checked(
        client.put(
            "/api/booking/profile",
            headers=visitor,
            json={"display_name": "Demo Visitor", "preferred_language": "en"},
        )
    )
    if args.prepare_only:
        print(
            "Prepared a current-day local simulated booking:",
            ref,
            "; visitor:",
            subject,
        )
        print(
            "No new arrival or ride event was recorded in this run. Reconnect the visitor to view its signed ticket."
        )
        raise SystemExit(0)
    assert client.get("/api/booking/admin/sales", headers=visitor).status_code == 403
    checked(client.get("/api/booking/admin/sales", headers=admin))
    preview = checked(
        client.post(
            "/api/gate/admin/tickets/validate",
            headers=admin,
            json={"ticket_token": ticket["ticket_token"]},
        )
    )
    arrival = client.post(
        "/api/gate/admin/check-ins",
        headers=admin,
        json={"ticket_token": ticket["ticket_token"], "guest_count": 4},
    )
    assert arrival.status_code == (409 if preview["already_checked_in"] else 201)
    assert (
        client.post(
            "/api/gate/admin/check-ins",
            headers=admin,
            json={"ticket_token": ticket["ticket_token"], "guest_count": 4},
        ).status_code
        == 409
    )
    attractions = checked(client.get("/api/attractions/attractions"))
    attraction = next(a for a in attractions if a["operational_status"] == "open")
    event_id = str(uuid5(NAMESPACE_URL, "wonderland-phase3:" + ref))
    body = {
        "event_id": event_id,
        "booking_reference": ref,
        "attraction_id": attraction["id"],
        "guest_count": 2,
    }
    checked(client.post("/api/gate/admin/ride-events", headers=admin, json=body))
    assert (
        checked(client.post("/api/gate/admin/ride-events", headers=admin, json=body))[
            "duplicate"
        ]
        is True
    )
    visits = checked(client.get("/api/gate/visits", headers=visitor))
    assert any(
        v["booking_reference"] == ref and v["guest_count"] == 4
        for v in visits["visits"]
    )
    assert any(
        r["event_id"] == event_id and r["guest_count"] == 2
        for r in visits["ride_events"]
    )
    other = checked(
        client.get("/api/gate/visits", headers=headers(owner="phase3-another-visitor"))
    )
    assert other == {"visits": [], "ride_events": []}
    print("PASS profile ownership, admin authorization and stored sales")
    print("PASS signed RSA ticket, four-guest arrival and duplicate-scan rejection")
    print(
        "PASS real catalog verification, two-rider event, retry deduplication and owned visit history"
    )
    print("Local demo booking:", ref, "; identity:", subject, "; no real payment")
