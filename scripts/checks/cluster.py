"""Exercise actual local Kubernetes business flow through the static gateway."""

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo
import httpx
import jwt
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "local_kubernetes", ROOT / "scripts/local-kubernetes.py"
)
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="phase5")
    parser.add_argument("--skip-analytics", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", args.scenario):
        raise SystemExit("Invalid demo scenario")
    k.guard()
    values = dotenv_values(k.ENVFILE)
    now = datetime.now(timezone.utc)
    today = datetime.now(ZoneInfo("Asia/Colombo")).date()
    subject = "phase5-demo-visitor"

    def headers(role="visitor"):
        token = jwt.encode(
            {
                "iss": "wonderland-local",
                "aud": "wonderland-local",
                "sub": subject,
                "role": role,
                "kind": "access",
                "iat": now,
                "exp": now + timedelta(minutes=10),
            },
            values["APP_AUTH_SECRET"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}

    def checked(response):
        if response.is_error:
            raise RuntimeError(
                f"Local gateway operation failed: HTTP {response.status_code}"
            )
        return response.json()

    with httpx.Client(base_url="http://127.0.0.1:5180", timeout=20) as client:
        for service in (
            ("attractions", "booking", "gate")
            if args.skip_analytics
            else ("attractions", "booking", "gate", "analytics")
        ):
            health = checked(client.get(f"/api/{service}/health/ready"))
            assert health["status"] == "ok"
        assert client.get("/").status_code == 200
        visitor = headers()
        admin = headers("admin")
        admin_base = "http://127.0.0.1:5181"
        assert client.get(admin_base + "/").status_code == 200
        credentials = json.loads(k.ENVFILE.with_suffix(".accounts.json").read_text())
        account = next(a for a in credentials if a["email"] == "admin@wonderland.local")
        session = checked(
            client.post(
                admin_base + "/api/booking/auth/local-login",
                json={
                    "email": account["email"],
                    "password": account["password"],
                    "portal": "admin",
                },
            )
        )
        staff = {"Authorization": "Bearer " + session["access_token"]}
        assert (
            checked(client.get(admin_base + "/api/booking/identity", headers=staff))[
                "role"
            ]
            == "admin"
        )
        if not args.skip_analytics:
            assert (
                client.get(
                    "/api/analytics/admin/analytics", headers=visitor
                ).status_code
                == 403
            )
        tiers = checked(client.get("/api/booking/ticket-tiers"))
        tier = next(t for t in tiers if t["name"] == "Family")
        booking = checked(
            client.post(
                "/api/booking/bookings",
                headers={**visitor, "Idempotency-Key": f"k8s-{today}-{args.scenario}"},
                json={
                    "tier_id": tier["id"],
                    "guest_count": 4,
                    "visit_date": (today + timedelta(days=1)).isoformat(),
                    "time_slot": "09:00",
                },
            )
        )
        ref = booking["reference"]
        if booking["status"] == "pending":
            # Development-only fixture: model a booking made earlier for today.
            # Reference is server-produced and validated before SQL interpolation.
            if not re.fullmatch(r"WL-[A-F0-9]{32}", ref):
                raise RuntimeError("Unexpected reference")
            sql = f"UPDATE booking.bookings SET visit_date='{today}' WHERE reference='{ref}' AND owner_id='{subject}' AND status='pending';"
            k.kubectl(
                "exec",
                "postgres-0",
                "--",
                "psql",
                "-U",
                "wonderland_owner",
                "-d",
                "wonderland",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                sql,
                stdout=subprocess.DEVNULL,
            )
            checked(
                client.post(f"/api/booking/bookings/{ref}/checkout", headers=visitor)
            )
            checked(
                client.post(f"/api/booking/bookings/{ref}/sandbox-pay", headers=visitor)
            )
        ticket = checked(
            client.get(f"/api/booking/bookings/{ref}/ticket", headers=visitor)
        )
        staff_ticket = checked(
            client.get(
                admin_base + f"/api/booking/admin/bookings/{ref}/ticket", headers=staff
            )
        )
        assert staff_ticket["booking"]["reference"] == ref
        assert (
            client.get(
                admin_base + f"/api/booking/admin/bookings/{ref}/ticket",
                headers=visitor,
            ).status_code
            == 403
        )
        ticket = staff_ticket
        print(
            "PASS separate admin portal, password sign-in and protected booking-reference lookup"
        )
        scan = {"ticket_token": ticket["ticket_token"], "guest_count": 4}
        arrival = client.post("/api/gate/admin/check-ins", headers=admin, json=scan)
        assert arrival.status_code in (201, 409)
        assert (
            client.post(
                "/api/gate/admin/check-ins", headers=admin, json=scan
            ).status_code
            == 409
        )
        attraction = next(
            a
            for a in checked(client.get("/api/attractions/attractions"))
            if a["operational_status"] == "open"
        )
        body = {
            "event_id": str(uuid5(NAMESPACE_URL, "wonderland-k8s:" + ref)),
            "booking_reference": ref,
            "attraction_id": attraction["id"],
            "guest_count": 2,
        }
        checked(client.post("/api/gate/admin/ride-events", headers=admin, json=body))
        assert checked(
            client.post("/api/gate/admin/ride-events", headers=admin, json=body)
        )["duplicate"]
        visits = checked(client.get("/api/gate/visits", headers=visitor))
        assert any(v["booking_reference"] == ref for v in visits["visits"])
        if args.skip_analytics:
            print("PASS Kubernetes booking, gate and rides while analytics is offline")
            return
        for _ in range(30):
            data = checked(client.get("/api/analytics/admin/analytics", headers=admin))
            if data["unpublished_events"] == 0 and not any(
                r["status"] != "done" and r["events"] for r in data["pipeline"]
            ):
                break
            time.sleep(1)
        else:
            raise RuntimeError("Kubernetes reporting backlog did not drain")
        assert sum(int(r["purchased_tickets"]) for r in data["tickets_by_tier"]) >= 1
        assert len(data["busiest_quiet_hours"]) == 9
        print(
            "PASS Kubernetes gateway, service discovery, simulated payment, RSA ticket, arrival, ride retry and stored analytics"
        )
        print("Local Kubernetes demo reference:", ref)
    # Reconcile all source/fact tables in the isolated Kubernetes database.
    sql = "SELECT (SELECT count(*) FROM booking.bookings WHERE status='confirmed')=(SELECT count(*) FROM reporting.purchases) AND (SELECT coalesce(sum(amount_cents),0) FROM booking.bookings WHERE status='confirmed')=(SELECT coalesce(sum(amount_cents),0) FROM reporting.purchases) AND (SELECT coalesce(sum(guest_count),0) FROM visits.check_ins)=(SELECT coalesce(sum(guest_count),0) FROM reporting.arrivals) AND (SELECT coalesce(sum(guest_count),0) FROM visits.ride_events)=(SELECT coalesce(sum(guest_count),0) FROM reporting.rides);"
    result = k.kubectl(
        "exec",
        "postgres-0",
        "--",
        "psql",
        "-U",
        "wonderland_owner",
        "-d",
        "wonderland",
        "-tAc",
        sql,
        capture_output=True,
    ).stdout.strip()
    assert result == "t"
    print("PASS Kubernetes reporting/source reconciliation")


if __name__ == "__main__":
    main()
