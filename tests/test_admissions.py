import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
from pydantic import SecretStr
import pytest
from sqlalchemy import text

from conftest import load_service
from test_domain import create, checkout


@pytest.fixture
def admissions(domain, monkeypatch, rsa_keys):
    private, public = rsa_keys
    owner_secret = "phase3-owner-hmac-testing-key-32-characters"
    for key, value in {
        "APP_TICKET_PUBLIC_KEY_B64": base64.b64encode(public).decode(),
        "APP_TICKET_OWNER_SECRET": owner_secret,
    }.items():
        monkeypatch.setenv(key, value)
    settings = domain["module"].settings
    settings.ticket_private_key_b64 = SecretStr(base64.b64encode(private).decode())
    settings.ticket_public_key_b64 = base64.b64encode(public).decode()
    settings.ticket_owner_secret = SecretStr(owner_secret)
    monkeypatch.delenv("APP_TICKET_PRIVATE_KEY_B64", raising=False)
    gate = load_service("gate-ride-service")
    gate.app.state.catalog = SimpleNamespace(
        get=lambda attraction_id, **_: {
            "id": str(attraction_id),
            "name": "Test Coaster",
            "operational_status": "open",
        }
    )
    with TestClient(gate.app) as client:
        yield {**domain, "gate": client, "gate_module": gate, "public": public}
    gate.app.state.engine.dispose()


def paid_today(ctx, subject="visitor-one"):
    booking = create(ctx, subject=subject).json()
    ref = booking["reference"]
    # Seed a booking made earlier for today, independent of the current test clock/slot.
    with ctx["engine"].begin() as conn:
        conn.execute(
            text("UPDATE booking.bookings SET visit_date=:day WHERE reference=:ref"),
            {"day": datetime.now(ZoneInfo("Asia/Colombo")).date(), "ref": ref},
        )
    headers = ctx["headers"](subject)
    assert (
        ctx["booking"].post(f"/bookings/{ref}/checkout", headers=headers).status_code
        == 200
    )
    assert (
        ctx["booking"].post(f"/bookings/{ref}/sandbox-pay", headers=headers).status_code
        == 200
    )
    result = ctx["booking"].get(f"/bookings/{ref}/ticket", headers=headers)
    assert result.status_code == 200
    return result.json()


def arrive(ctx, ticket, guests=4):
    return ctx["gate"].post(
        "/admin/check-ins",
        json={"ticket_token": ticket["ticket_token"], "guest_count": guests},
        headers=ctx["headers"]("staff", "admin"),
    )


def test_profile_is_owned_and_cannot_change_role(admissions):
    client = admissions["booking"]
    headers = admissions["headers"]()
    assert (
        client.put(
            "/profile",
            json={"display_name": "Alex", "preferred_language": "si"},
            headers=headers,
        ).status_code
        == 200
    )
    assert client.get("/profile", headers=headers).json()["display_name"] == "Alex"
    assert (
        client.get("/profile", headers=admissions["headers"]("someone-else")).json()[
            "display_name"
        ]
        == ""
    )
    assert (
        client.put(
            "/profile", json={"display_name": "Alex", "role": "admin"}, headers=headers
        ).status_code
        == 422
    )


def test_tier_lifecycle_preserves_booking_snapshot(admissions):
    client = admissions["booking"]
    admin = admissions["headers"]("staff", "admin")
    booking = create(admissions).json()
    tier = {
        "name": "Family revised",
        "min_guests": 2,
        "max_guests": 4,
        "price_cents": 15500,
        "active": False,
    }
    path = "/admin/ticket-tiers/" + str(UUID(int=3))
    assert (
        client.put(path, json=tier, headers=admissions["headers"]()).status_code == 403
    )
    assert client.put(path, json=tier, headers=admin).status_code == 200
    assert len(client.get("/ticket-tiers").json()) == 3
    assert (
        client.get(
            "/bookings/" + booking["reference"], headers=admissions["headers"]()
        ).json()["amount_cents"]
        == 14000
    )
    assert create(admissions).status_code == 422
    assert (
        client.post(
            "/admin/ticket-tiers",
            json={**tier, "name": "Test pass", "active": True},
            headers=admin,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/admin/ticket-tiers", json={**tier, "name": "Test pass"}, headers=admin
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/admin/ticket-tiers",
            json={**tier, "min_guests": 5, "max_guests": 4},
            headers=admin,
        ).status_code
        == 422
    )
    assert len(client.get("/admin/ticket-tiers", headers=admin).json()) == 5


def test_gate_counts_guests_not_bookings_and_rejects_duplicate(admissions):
    ticket = paid_today(admissions)
    assert (
        admissions["gate"]
        .post(
            "/admin/check-ins",
            json={"ticket_token": ticket["ticket_token"], "guest_count": 4},
            headers=admissions["headers"](),
        )
        .status_code
        == 403
    )
    assert arrive(admissions, ticket, 3).status_code == 422
    assert arrive(admissions, ticket).status_code == 201
    assert arrive(admissions, ticket).status_code == 409
    totals = (
        admissions["gate"]
        .get("/admin/activity", headers=admissions["headers"]("staff", "admin"))
        .json()
    )
    assert totals["arriving_guests"] == 4 and totals["arrival_bookings"] == 1
    with admissions["engine"].connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM visits.outbox WHERE event_type='visitor.arrived'"
                )
            ).scalar()
            == 1
        )


def test_concurrent_gate_scans_admit_once(admissions):
    ticket = paid_today(admissions)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: arrive(admissions, ticket), range(6)))
    assert sum(r.status_code == 201 for r in results) == 1
    assert sum(r.status_code == 409 for r in results) == 5


def test_gate_is_independent_of_booking_and_attractions_api(admissions):
    ticket = paid_today(admissions)
    original_engine = admissions["module"].app.state.engine
    admissions["module"].app.state.engine = None
    admissions["gate_module"].app.state.catalog = SimpleNamespace(
        get=lambda _, **kw: (_ for _ in ()).throw(
            AssertionError("Gate must not call catalog")
        )
    )
    try:
        assert arrive(admissions, ticket).status_code == 201
    finally:
        admissions["module"].app.state.engine = original_engine


def test_gate_rejects_wrong_date_tampered_and_legacy_tickets(admissions, rsa_keys):
    future = create(admissions).json()["reference"]
    checkout(admissions, future)
    admissions["booking"].post(
        f"/bookings/{future}/sandbox-pay", headers=admissions["headers"]()
    )
    ticket = (
        admissions["booking"]
        .get(f"/bookings/{future}/ticket", headers=admissions["headers"]())
        .json()
    )
    assert arrive(admissions, ticket).status_code == 422
    ticket = paid_today(admissions)
    parts = ticket["ticket_token"].split(".")
    payload = json.loads(
        base64.urlsafe_b64decode(parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4))
    )
    payload["guest_count"] = 5
    parts[1] = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    assert (
        arrive(admissions, {**ticket, "ticket_token": ".".join(parts)}).status_code
        == 400
    )
    legacy = jwt.encode(
        {
            "iss": "wonderland-tickets",
            "aud": "wonderland-gate",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "phase2-legacy-testing-key" * 2,
        algorithm="HS256",
    )
    assert arrive(admissions, {"ticket_token": legacy}).status_code == 400


def test_gate_outbox_failure_rolls_back_arrival(admissions):
    ticket = paid_today(admissions)
    with admissions["engine"].begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE visits.outbox ADD CONSTRAINT reject_arrival CHECK(false) NOT VALID"
        )
    try:
        assert arrive(admissions, ticket).status_code == 503
        with admissions["engine"].connect() as conn:
            assert (
                conn.execute(text("SELECT count(*) FROM visits.check_ins")).scalar()
                == 0
            )
    finally:
        with admissions["engine"].begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE visits.outbox DROP CONSTRAINT reject_arrival"
            )
    assert arrive(admissions, ticket).status_code == 201


def ride(ctx, reference, event_id=None, guests=2):
    body = {
        "event_id": event_id or str(uuid4()),
        "booking_reference": reference,
        "attraction_id": str(UUID(int=101)),
        "guest_count": guests,
    }
    return ctx["gate"].post(
        "/admin/ride-events", json=body, headers=ctx["headers"]("staff", "admin")
    )


def test_ride_requires_arrival_and_bounded_party(admissions):
    ticket = paid_today(admissions)
    ref = ticket["booking"]["reference"]
    assert ride(admissions, ref).status_code == 422
    arrive(admissions, ticket)
    assert ride(admissions, ref, guests=5).status_code == 422
    event_id = str(uuid4())
    assert ride(admissions, ref, event_id).status_code == 201
    assert ride(admissions, ref, event_id).json()["duplicate"] is True
    assert ride(admissions, ref, event_id, guests=3).status_code == 409
    history = admissions["gate"].get("/visits", headers=admissions["headers"]()).json()
    assert len(history["visits"]) == 1 and len(history["ride_events"]) == 1
    assert admissions["gate"].get(
        "/visits", headers=admissions["headers"]("other")
    ).json() == {
        "visits": [],
        "ride_events": [],
    }


def test_ride_catalog_outage_is_fail_closed_but_gate_stays_available(admissions):
    ticket = paid_today(admissions)
    arrive(admissions, ticket)

    def unavailable(_, **kwargs):
        raise HTTPException(503, "simulated catalog outage")

    admissions["gate_module"].app.state.catalog = SimpleNamespace(get=unavailable)
    assert ride(admissions, ticket["booking"]["reference"]).status_code == 503
    with admissions["engine"].connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM visits.ride_events")).scalar() == 0
        )
    assert admissions["gate"].get("/health/live").status_code == 200


def test_concurrent_ride_event_retry_is_deduplicated(admissions):
    ticket = paid_today(admissions)
    arrive(admissions, ticket)
    event_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: ride(admissions, ticket["booking"]["reference"], event_id),
                range(6),
            )
        )
    assert all(r.status_code == 201 for r in results)
    assert sum(not r.json()["duplicate"] for r in results) == 1
    with admissions["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM visits.outbox WHERE event_type='ride.used'")
            ).scalar()
            == 1
        )


def test_admin_sales_use_confirmed_snapshot_and_reject_visitor(admissions):
    paid_today(admissions)
    create(admissions)
    client = admissions["booking"]
    assert (
        client.get("/admin/sales", headers=admissions["headers"]()).status_code == 403
    )
    rows = client.get(
        "/admin/sales", headers=admissions["headers"]("staff", "admin")
    ).json()
    assert (
        len(rows) == 1 and rows[0]["tickets"] == 1 and rows[0]["revenue_cents"] == 14000
    )


@pytest.fixture
def cognito(domain, monkeypatch, rsa_keys):
    private, public = rsa_keys
    settings = domain["module"].settings
    settings.auth_mode = "cognito"
    settings.cognito_region = "us-east-1"
    settings.cognito_user_pool_id = "us-east-1_OfflineTest"
    settings.cognito_client_id = "offlineclient"
    settings.cognito_admin_group = "administrators"
    client = jwt.PyJWKClient(settings.cognito_issuer + "/.well-known/jwks.json")
    jwk = json.loads(
        jwt.algorithms.RSAAlgorithm.to_jwk(serialization.load_pem_public_key(public))
    )
    jwk["kid"] = "offline-key"
    jwk["use"] = "sig"
    monkeypatch.setattr(client, "fetch_data", lambda: {"keys": [jwk]})
    domain["module"].app.state.jwks_client = client

    def token(headers=None, **changes):
        now = datetime.now(timezone.utc)
        claims = {
            "iss": settings.cognito_issuer,
            "sub": "cognito-visitor",
            "username": "visitor",
            "client_id": "offlineclient",
            "token_use": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            **changes,
        }
        value = jwt.encode(
            claims,
            private,
            algorithm="RS256",
            headers=headers or {"kid": "offline-key"},
        )
        return {"Authorization": "Bearer " + value}

    return domain, token


def test_cognito_real_rsa_verification_and_group_authorization_offline(cognito):
    ctx, headers = cognito
    client = ctx["booking"]
    assert client.get("/identity", headers=headers()).json()["mode"] == "cognito"
    assert client.get("/admin/sales", headers=headers()).status_code == 403
    assert (
        client.get(
            "/admin/sales", headers=headers(**{"cognito:groups": ["administrators"]})
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/admin/sales", headers=headers(**{"cognito:groups": ["other"]})
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://untrusted.example"},
        {"client_id": "wrong-client"},
        {"token_use": "id"},
        {"exp": 1},
        {"username": None},
        {"cognito:groups": "administrators"},
    ],
)
def test_cognito_rejects_bad_claims(cognito, changes):
    ctx, headers = cognito
    assert (
        ctx["booking"].get("/identity", headers=headers(**changes)).status_code == 401
    )


def test_cognito_unknown_key_and_key_fetch_failure(cognito, monkeypatch):
    ctx, headers = cognito
    client = ctx["booking"]
    assert (
        client.get(
            "/identity", headers=headers(headers={"kid": "unknown-key"})
        ).status_code
        == 401
    )

    def offline(_):
        raise jwt.PyJWKClientConnectionError("offline")

    monkeypatch.setattr(
        ctx["module"].app.state.jwks_client, "get_signing_key_from_jwt", offline
    )
    assert client.get("/identity", headers=headers()).status_code == 503


def test_cognito_rejects_algorithm_confusion(cognito):
    ctx, _ = cognito
    fake = jwt.encode(
        {"sub": "attacker", "role": "admin"},
        "untrusted-testing-secret" * 2,
        algorithm="HS256",
        headers={"kid": "offline-key"},
    )
    assert (
        ctx["booking"]
        .get("/identity", headers={"Authorization": "Bearer " + fake})
        .status_code
        == 401
    )


def test_ride_outbox_failure_rolls_back_and_can_retry(admissions):
    ticket = paid_today(admissions)
    arrive(admissions, ticket)
    event_id = str(uuid4())
    ref = ticket["booking"]["reference"]
    with admissions["engine"].begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE visits.outbox ADD CONSTRAINT reject_ride CHECK(false) NOT VALID"
        )
    try:
        assert ride(admissions, ref, event_id).status_code == 503
        with admissions["engine"].connect() as conn:
            assert (
                conn.execute(text("SELECT count(*) FROM visits.ride_events")).scalar()
                == 0
            )
    finally:
        with admissions["engine"].begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE visits.outbox DROP CONSTRAINT reject_ride"
            )
    assert ride(admissions, ref, event_id).status_code == 201


def test_cognito_role_claim_cannot_replace_admin_group(cognito):
    ctx, headers = cognito
    assert (
        ctx["booking"].get("/admin/sales", headers=headers(role="admin")).status_code
        == 403
    )
    ctx["module"].settings.cognito_audience = "wonderland-api"
    assert (
        ctx["booking"].get("/identity", headers=headers(aud="wrong-api")).status_code
        == 401
    )
    assert (
        ctx["booking"]
        .get("/identity", headers=headers(aud="wonderland-api"))
        .status_code
        == 200
    )


def test_catalog_client_checks_status_and_propagates_request_id(
    admissions, monkeypatch
):
    import httpx

    routes = importlib.import_module(admissions["gate_module"].__package__ + ".routes")
    original = httpx.Client
    mode = ["closed"]
    seen = []
    attraction_id = UUID(int=101)

    def handle(request):
        seen.append(request.headers.get("X-Request-ID"))
        return httpx.Response(
            200,
            json={
                "id": str(attraction_id),
                "name": "Coaster",
                "operational_status": mode[0],
            },
        )

    monkeypatch.setattr(
        routes.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    lookup = routes.CatalogLookup("http://catalog.test")
    with pytest.raises(HTTPException) as error:
        lookup.get(attraction_id, request_id="ride-trace-1")
    assert error.value.status_code == 422
    mode[0] = "open"
    assert lookup.get(attraction_id, request_id="ride-trace-2")["name"] == "Coaster"
    assert seen == ["ride-trace-1", "ride-trace-2"]


def test_gate_readiness_requires_verification_and_ownership_keys(admissions):
    assert admissions["gate"].get("/health/ready").status_code == 200
    settings = admissions["gate_module"].settings
    public = settings.ticket_public_key_b64
    settings.ticket_public_key_b64 = None
    assert admissions["gate"].get("/health/ready").status_code == 503
    assert admissions["gate"].get("/health/live").status_code == 200
    settings.ticket_public_key_b64 = public
    settings.ticket_owner_secret = None
    assert admissions["gate"].get("/health/ready").status_code == 503


def test_renaming_does_not_split_tier_or_attraction_totals(admissions):
    ticket = paid_today(admissions)
    arrive(admissions, ticket)
    ref = ticket["booking"]["reference"]
    assert ride(admissions, ref).status_code == 201
    admissions["gate_module"].app.state.catalog = SimpleNamespace(
        get=lambda attraction_id, **kw: {
            "id": str(attraction_id),
            "name": "Renamed Coaster",
            "operational_status": "open",
        }
    )
    assert ride(admissions, ref).status_code == 201
    with admissions["engine"].begin() as conn:
        conn.execute(
            text("UPDATE booking.ticket_tiers SET name='Renamed Family' WHERE id=:id"),
            {"id": UUID(int=3)},
        )
    paid_today(admissions)
    sales = (
        admissions["booking"]
        .get("/admin/sales", headers=admissions["headers"]("staff", "admin"))
        .json()
    )
    assert (
        len(sales) == 1
        and sales[0]["tickets"] == 2
        and sales[0]["revenue_cents"] == 28000
    )
    rides = (
        admissions["gate"]
        .get("/admin/activity", headers=admissions["headers"]("staff", "admin"))
        .json()["rides"]
    )
    assert len(rides) == 1 and rides[0]["riders"] == 4 and rides[0]["ride_events"] == 2
