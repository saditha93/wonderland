"""Real HTTP local simulator demo; no external payment call, no tokens printed."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
import httpx
import jwt
from wonderland_common.config import Settings

load_dotenv(Path(__file__).resolve().parents[1] / "secrets/local.env")
settings = Settings()
if (
    settings.environment not in {"local", "test"}
    or settings.auth_mode != "local"
    or settings.payment_provider != "local"
):
    raise SystemExit(
        "This smoke demo runs only with local signed identity and local payment simulator"
    )
now = datetime.now(timezone.utc)
token = jwt.encode(
    {
        "sub": "demo-visitor",
        "role": "visitor",
        "kind": "access",
        "iss": "wonderland-local",
        "aud": "wonderland-local",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    },
    settings.auth_secret.get_secret_value(),
    algorithm="HS256",
)
visit_date = (
    datetime.now(ZoneInfo("Asia/Colombo")).date() + timedelta(days=1)
).isoformat()
with httpx.Client(
    base_url="http://127.0.0.1:5173",
    headers={"Authorization": "Bearer " + token},
    timeout=10,
) as client:
    catalog = client.get("/api/attractions/attractions")
    catalog.raise_for_status()
    assert len(catalog.json()) >= 1
    tiers = client.get("/api/booking/ticket-tiers")
    tiers.raise_for_status()
    family = next(r for r in tiers.json() if r["name"] == "Family")
    command = {
        "tier_id": family["id"],
        "guest_count": 4,
        "visit_date": visit_date,
        "time_slot": "09:00",
    }
    key = "smoke-" + hashlib.sha256(str(command).encode()).hexdigest()[:32]
    result = client.post(
        "/api/booking/bookings", json=command, headers={"Idempotency-Key": key}
    )
    result.raise_for_status()
    booking = result.json()
    ref = booking["reference"]
    print("PASS catalog, stored tiers and booking command through frontend proxy")
    repeat = client.post(
        "/api/booking/bookings", json=command, headers={"Idempotency-Key": key}
    )
    repeat.raise_for_status()
    assert repeat.json()["reference"] == ref
    print("PASS retry returns the same booking")
    if booking["status"] == "pending":
        checkout = client.post(f"/api/booking/bookings/{ref}/checkout")
        checkout.raise_for_status()
        assert checkout.json()["provider"] == "local"
    paid = client.post(f"/api/booking/bookings/{ref}/sandbox-pay")
    paid.raise_for_status()
    ticket = client.get(f"/api/booking/bookings/{ref}/ticket")
    ticket.raise_for_status()
    assert ticket.json()["booking"]["payment_status"] == "paid"
    jwt.decode(
        ticket.json()["ticket_token"],
        settings.ticket_secret.get_secret_value(),
        algorithms=["HS256"],
        audience="wonderland-gate",
        issuer="wonderland-tickets",
    )
    print(
        "PASS signed local payment, confirmed booking, signed QR ticket and stored history"
    )
    history = client.get("/api/booking/bookings")
    history.raise_for_status()
    assert any(r["reference"] == ref for r in history.json())
    print("Demo booking:", ref, "(local simulator only; no real payment)")
