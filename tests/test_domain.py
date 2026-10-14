import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import jwt
import pytest
from sqlalchemy import text
from fastapi import HTTPException

TOMORROW = lambda: (
    datetime.now(ZoneInfo("Asia/Colombo")).date() + timedelta(days=1)
).isoformat()


def command(tier=3, guests=4, **changes):
    return {
        "tier_id": str(UUID(int=tier)),
        "guest_count": guests,
        "visit_date": TOMORROW(),
        "time_slot": "09:00",
        **changes,
    }


def create(domain, key=None, body=None, subject="visitor-one"):
    return domain["booking"].post(
        "/bookings",
        json=body or command(),
        headers={**domain["headers"](subject), "Idempotency-Key": key or uuid4().hex},
    )


def checkout(domain, reference):
    return domain["booking"].post(
        f"/bookings/{reference}/checkout", headers=domain["headers"]()
    )


def event(domain, reference, **changes):
    module = domain["module"]
    session = {
        "id": "local_" + reference,
        "metadata": {"booking_reference": reference},
        "amount_total": 14000,
        "currency": "usd",
        "payment_status": "paid",
        "status": "complete",
    }
    session.update(changes.pop("session", {}))
    data = {
        "id": "evt_" + reference,
        "livemode": False,
        "type": "checkout.session.completed",
        "data": {"object": session},
        **changes,
    }
    raw = json.dumps(data).encode()
    # Main imports router only; use the actual payments module via its package.
    import importlib

    payments = importlib.import_module(module.__package__ + ".payments")
    signature = payments.local_signature(
        raw, module.settings.local_webhook_secret.get_secret_value()
    )
    return raw, signature


def post_event(domain, raw, signature, header="X-Sandbox-Signature"):
    return domain["booking"].post(
        "/payments/webhook",
        content=raw,
        headers={header: signature, "Content-Type": "application/json"},
    )


def count(domain, table):
    assert table in {"bookings", "payment_events", "outbox"}
    with domain["engine"].connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM booking.{table}")).scalar_one()


def test_catalog_search_and_detail(domain):
    client = domain["attractions"]
    rows = client.get("/attractions").json()
    assert len(rows) == 6
    assert len(client.get("/attractions?q=water").json()) == 1
    row = client.get("/attractions/" + str(UUID(int=101))).json()
    assert row["minimum_height_cm"] == 140 and row["thrill_level"] == "high"
    assert client.get("/attractions/not-a-uuid").status_code == 422


def test_admin_catalog_mutations_and_retirement(domain):
    client = domain["attractions"]
    admin = domain["headers"]("staff", "admin")
    body = {
        "name": "Test Ride",
        "description": "A suitable attraction description.",
        "category": "Family",
        "thrill_level": "gentle",
        "minimum_age": 0,
        "minimum_height_cm": 0,
    }
    assert (
        client.post("/attractions", json=body, headers=domain["headers"]()).status_code
        == 403
    )
    assert client.post("/attractions", json=body).status_code == 401
    created = client.post("/attractions", json=body, headers=admin)
    assert created.status_code == 201
    ref = created.json()["id"]
    assert (
        client.put(
            "/attractions/" + ref,
            json={**body, "minimum_height_cm": 110},
            headers=admin,
        ).json()["minimum_height_cm"]
        == 110
    )
    assert (
        client.delete("/attractions/" + ref, headers=admin).json()["operational_status"]
        == "retired"
    )
    assert client.get("/attractions/" + ref).status_code == 404


def test_stored_initial_prices(domain):
    rows = domain["booking"].get("/ticket-tiers").json()
    assert [(r["name"], r["price_cents"]) for r in rows] == [
        ("Individual", 4000),
        ("Couple", 7500),
        ("Family", 14000),
        ("Group", 16500),
    ]


@pytest.mark.parametrize(
    "body",
    [
        command(1, 2),
        command(2, 1),
        command(3, 5),
        command(4, 6),
        command(3, True),
        command(3, 4, amount_cents=1),
        command(3, 4, time_slot="02:00"),
        command(3, 4, visit_date="2020-01-01"),
        command(999, 1),
    ],
)
def test_booking_rejects_invalid_input_and_client_price(domain, body):
    assert create(domain, body=body).status_code == 422
    assert count(domain, "bookings") == 0


def test_price_snapshot_idempotent_retry_and_admin_only_price(domain):
    first = create(domain, key="snapshot-key")
    assert first.status_code == 201
    client = domain["booking"]
    path = "/ticket-tiers/" + str(UUID(int=3))
    assert (
        client.patch(
            path, json={"price_cents": 15000}, headers=domain["headers"]()
        ).status_code
        == 403
    )
    assert (
        client.patch(
            path,
            json={"price_cents": 15000},
            headers=domain["headers"]("staff", "admin"),
        ).status_code
        == 200
    )
    retry = create(domain, key="snapshot-key")
    assert retry.status_code == 200
    assert (
        retry.json()["reference"] == first.json()["reference"]
        and retry.json()["amount_cents"] == 14000
    )
    new = create(domain).json()
    assert new["amount_cents"] == 15000 and new["tier_revision"] == 2
    assert create(domain, key="snapshot-key", body=command(3, 3)).status_code == 409


def test_concurrent_booking_requests_create_one_record(domain):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: create(domain, key="concurrent-command"), range(6))
        )
    assert all(r.status_code in {200, 201} for r in results)
    assert len({r.json()["reference"] for r in results}) == 1
    assert count(domain, "bookings") == 1


def test_history_and_ticket_ownership(domain):
    first = create(domain).json()
    second = create(domain, subject="visitor-two").json()
    client = domain["booking"]
    assert len(client.get("/bookings", headers=domain["headers"]()).json()) == 1
    for suffix in ["", "/ticket", "/checkout", "/sandbox-pay"]:
        method = client.post if suffix in {"/checkout", "/sandbox-pay"} else client.get
        assert (
            method(
                "/bookings/" + second["reference"] + suffix, headers=domain["headers"]()
            ).status_code
            == 404
        )
    assert (
        client.get(
            "/bookings/" + first["reference"] + "/ticket", headers=domain["headers"]()
        ).status_code
        == 409
    )


def test_confirm_once_and_signed_qr_ticket(domain):
    ref = create(domain).json()["reference"]
    assert checkout(domain, ref).json()["provider"] == "local"
    raw, sig = event(domain, ref)
    assert post_event(domain, raw, sig).json()["duplicate"] is False
    assert post_event(domain, raw, sig).json()["duplicate"] is True
    raw2, sig2 = event(domain, ref, id="evt_second_valid_delivery")
    assert post_event(domain, raw2, sig2).json()["duplicate"] is True
    assert count(domain, "outbox") == 1
    ticket = (
        domain["booking"]
        .get(f"/bookings/{ref}/ticket", headers=domain["headers"]())
        .json()
    )
    assert ticket["booking"]["status"] == "confirmed" and ticket[
        "qr_data_url"
    ].startswith("data:image/png;base64,")
    claims = jwt.decode(
        ticket["ticket_token"],
        base64.b64decode(domain["module"].settings.ticket_public_key_b64),
        algorithms=["RS256"],
        audience="wonderland-gate",
        issuer="wonderland-tickets",
    )
    assert claims["kind"] == "ticket" and claims["ref"] == ref and "sub" not in claims
    assert (
        domain["booking"]
        .get("/bookings", headers={"Authorization": "Bearer " + ticket["ticket_token"]})
        .status_code
        == 401
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"session": {"amount_total": 1}},
        {"session": {"currency": "eur"}},
        {"session": {"id": "wrong-session"}},
        {"livemode": True},
        {"livemode": None},
        {"session": {"amount_total": True}},
    ],
)
def test_invalid_payments_leave_pending(domain, changes):
    ref = create(domain).json()["reference"]
    checkout(domain, ref)
    raw, sig = event(domain, ref, **changes)
    assert post_event(domain, raw, sig).status_code == 400
    assert count(domain, "payment_events") == 0 and count(domain, "outbox") == 0
    assert (
        domain["booking"]
        .get(f"/bookings/{ref}", headers=domain["headers"]())
        .json()["status"]
        == "pending"
    )


def test_unsigned_tampered_stale_and_unpaid_events(domain):
    import importlib

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    ref = create(domain).json()["reference"]
    checkout(domain, ref)
    raw, sig = event(domain, ref)
    assert post_event(domain, raw, "").status_code == 400
    assert post_event(domain, raw + b" ", sig).status_code == 400
    stale = payments.local_signature(
        raw,
        domain["module"].settings.local_webhook_secret.get_secret_value(),
        timestamp=1,
    )
    assert post_event(domain, raw, stale).status_code == 400
    raw, sig = event(domain, ref, session={"payment_status": "unpaid"})
    assert post_event(domain, raw, sig).json()["ignored"] is True
    assert count(domain, "outbox") == 0


def test_concurrent_webhooks_confirm_once(domain):
    ref = create(domain).json()["reference"]
    checkout(domain, ref)
    raw, sig = event(domain, ref)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: post_event(domain, raw, sig), range(6)))
    assert all(r.status_code == 200 for r in results)
    assert sum(not r.json()["duplicate"] for r in results) == 1
    assert count(domain, "outbox") == 1 and count(domain, "payment_events") == 1


def test_atomic_confirmation_rolls_back_when_outbox_fails(domain):
    ref = create(domain).json()["reference"]
    checkout(domain, ref)
    raw, sig = event(domain, ref)
    with domain["engine"].begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE booking.outbox ADD CONSTRAINT test_reject_insert CHECK (false) NOT VALID"
        )
    try:
        assert post_event(domain, raw, sig).status_code == 503
        assert count(domain, "payment_events") == 0 and count(domain, "outbox") == 0
        assert (
            domain["booking"]
            .get(f"/bookings/{ref}", headers=domain["headers"]())
            .json()["status"]
            == "pending"
        )
    finally:
        with domain["engine"].begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE booking.outbox DROP CONSTRAINT test_reject_insert"
            )
    assert post_event(domain, raw, sig).status_code == 200


def test_local_simulator_and_engine_reconnect(domain):
    ref = create(domain).json()["reference"]
    checkout(domain, ref)
    path = f"/bookings/{ref}/sandbox-pay"
    assert domain["booking"].post(path, headers=domain["headers"]()).status_code == 200
    domain["module"].app.state.engine.dispose()
    assert (
        domain["booking"]
        .get(f"/bookings/{ref}", headers=domain["headers"]())
        .json()["payment_status"]
        == "paid"
    )
    assert (
        domain["booking"].post(path, headers=domain["headers"]()).json()["duplicate"]
        is True
    )
    assert count(domain, "outbox") == 1


def test_expired_and_wrong_kind_identity_rejected(domain):
    assert (
        domain["booking"].get("/bookings", headers=domain["headers"](exp=1)).status_code
        == 401
    )
    assert (
        domain["booking"]
        .get("/bookings", headers=domain["headers"](kind="ticket"))
        .status_code
        == 401
    )
    assert (
        domain["booking"]
        .get("/bookings", headers={"Authorization": "Bearer invalid"})
        .status_code
        == 401
    )


def test_seed_and_migration_repeat_without_overwriting_prices(domain):
    from scripts.db_migrate import migrate, seed

    client = domain["booking"]
    path = "/ticket-tiers/" + str(UUID(int=3))
    client.patch(
        path, json={"price_cents": 16000}, headers=domain["headers"]("staff", "admin")
    )
    migrate(domain["engine"])
    seed(domain["engine"])
    assert (
        next(r for r in client.get("/ticket-tiers").json() if r["name"] == "Family")[
            "price_cents"
        ]
        == 16000
    )


def test_stripe_test_adapter_and_sdk_signature_without_network(domain, monkeypatch):
    import importlib

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    settings = domain["module"].settings
    settings.payment_provider = "stripe"
    from pydantic import SecretStr

    settings.stripe_webhook_secret = SecretStr("whsec_unit_test_only")
    seen = []

    def fake_checkout(settings, booking):
        seen.append(booking["amount_cents"])
        return SimpleNamespace(
            id="cs_test_" + booking["reference"],
            url="https://checkout.stripe.com/test-session",
            livemode=False,
        )

    monkeypatch.setattr(payments, "create_stripe_checkout", fake_checkout)
    ref = create(domain).json()["reference"]
    assert checkout(domain, ref).json()["provider"] == "stripe"
    assert seen == [14000]
    assert (
        domain["booking"]
        .post(f"/bookings/{ref}/sandbox-pay", headers=domain["headers"]())
        .status_code
        == 404
    )
    raw, _ = event(domain, ref, session={"id": "cs_test_" + ref})
    sig = payments.local_signature(
        raw, settings.stripe_webhook_secret.get_secret_value()
    )
    assert post_event(domain, raw, sig, header="Stripe-Signature").status_code == 200
    assert count(domain, "outbox") == 1


def test_circuit_breaker_opens_and_half_open_recovers(domain):
    import importlib

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    now = [0]
    breaker = payments.CircuitBreaker(threshold=2, cooldown=10, clock=lambda: now[0])

    def failed():
        raise RuntimeError("simulated failure")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(failed)
    with pytest.raises(HTTPException):
        breaker.call(lambda: "not called")
    now[0] = 11
    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.failures == 0 and breaker.opened_at is None


def test_local_auth_forbidden_outside_local_environment():
    from wonderland_common.config import Settings

    with pytest.raises(ValueError):
        Settings(environment="production", auth_mode="local", auth_secret="x" * 48)
    with pytest.raises(ValueError):
        Settings(stripe_secret_key="sk_live_FORBIDDEN")


def test_event_id_collision_does_not_confirm_another_booking(domain):
    first = create(domain).json()["reference"]
    second = create(domain).json()["reference"]
    checkout(domain, first)
    checkout(domain, second)
    raw, sig = event(domain, first, id="same-provider-event-id")
    assert post_event(domain, raw, sig).status_code == 200
    raw, sig = event(domain, second, id="same-provider-event-id")
    assert post_event(domain, raw, sig).status_code == 409
    assert (
        domain["booking"]
        .get("/bookings/" + second, headers=domain["headers"]())
        .json()["status"]
        == "pending"
    )
    assert count(domain, "outbox") == 1


def test_invalid_webhook_shape_and_payload_limit(domain):
    import importlib

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    raw = b"[]"
    sig = payments.local_signature(
        raw, domain["module"].settings.local_webhook_secret.get_secret_value()
    )
    assert post_event(domain, raw, sig).status_code == 400
    assert post_event(domain, b"x" * 262145, "").status_code == 413


def test_readiness_checks_real_schema_and_database(domain):
    assert domain["booking"].get("/health/ready").json()["scope"] == "database"
    assert domain["attractions"].get("/health/ready").status_code == 200
    engine = domain["module"].app.state.engine
    domain["module"].app.state.engine = None
    assert domain["booking"].get("/health/ready").status_code == 503
    assert domain["booking"].get("/health/live").status_code == 200
    domain["module"].app.state.engine = engine


def test_stripe_outage_keeps_booking_pending_and_reuses_checkout(domain, monkeypatch):
    import importlib
    import stripe

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    domain["module"].settings.payment_provider = "stripe"
    calls = []

    def offline(settings, booking):
        calls.append(1)
        raise stripe.APIConnectionError("simulated offline")

    monkeypatch.setattr(payments, "create_stripe_checkout", offline)
    ref = create(domain).json()["reference"]
    for _ in range(4):
        assert checkout(domain, ref).status_code == 503
    assert len(calls) == 3  # fourth request is blocked by open circuit
    assert (
        domain["booking"]
        .get("/bookings/" + ref, headers=domain["headers"]())
        .json()["status"]
        == "pending"
    )
    assert count(domain, "outbox") == 0


def test_stripe_sdk_request_uses_stored_price_and_idempotency(domain, monkeypatch):
    import importlib
    from pydantic import SecretStr

    payments = importlib.import_module(domain["module"].__package__ + ".payments")
    seen = {}

    class Sessions:
        def create(self, params, options):
            seen.update(params=params, options=options)
            return SimpleNamespace(
                id="cs_test_example",
                url="https://checkout.stripe.com/test-example",
                livemode=False,
            )

    class Client:
        def __init__(self, key, **kwargs):
            assert key.startswith("sk_test_")
            assert kwargs["max_network_retries"] == 1
            self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=Sessions()))

    monkeypatch.setattr(payments.stripe, "StripeClient", Client)
    settings = domain["module"].settings
    settings.stripe_secret_key = SecretStr("sk_test_mock_only")
    booking = create(domain).json()
    payments.create_stripe_checkout(settings, booking)
    assert seen["params"]["line_items"][0]["price_data"]["unit_amount"] == 14000
    assert seen["params"]["line_items"][0]["quantity"] == 1
    assert seen["options"]["idempotency_key"] == "checkout-" + booking["reference"]
    assert seen["params"]["metadata"]["booking_reference"] == booking["reference"]


def test_invalid_configuration_does_not_render_secret_values():
    from wonderland_common.config import Settings

    sentinel = "sk_live_PRIVATE_CONFIG_SENTINEL"
    with pytest.raises(ValueError) as error:
        Settings(stripe_secret_key=sentinel)
    assert sentinel not in str(error.value)
