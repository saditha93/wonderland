"""Guest checkout retains the same payment and ownership boundaries as accounts."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest


def command():
    return {
        "tier_id": str(UUID(int=3)),
        "guest_count": 4,
        "visit_date": (
            datetime.now(ZoneInfo("Asia/Colombo")).date() + timedelta(days=1)
        ).isoformat(),
        "time_slot": "09:00",
    }


@pytest.mark.parametrize("mode", ["local", "cognito"])
def test_guest_purchase_is_private_and_payment_is_required(domain, mode):
    client = domain["booking"]
    settings = domain["module"].app.state.settings
    domain["module"].app.state.settings = settings.model_copy(
        update={"auth_mode": mode}
    )
    guest = {"Authorization": "Guest " + secrets.token_hex(32)}
    other = {"Authorization": "Guest " + secrets.token_hex(32)}
    response = client.post(
        "/bookings", json=command(), headers={**guest, "Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 201
    ref = response.json()["reference"]
    assert client.get("/bookings", headers=guest).json()[0]["reference"] == ref
    assert client.get("/bookings", headers=other).json() == []
    for suffix in ["", "/ticket"]:
        assert client.get(f"/bookings/{ref}{suffix}", headers=other).status_code == 404
        assert client.get(f"/bookings/{ref}{suffix}").status_code == 401
    assert client.post(f"/bookings/{ref}/checkout", headers=other).status_code == 404
    assert client.get(f"/bookings/{ref}/ticket", headers=guest).status_code == 409
    assert client.get("/profile", headers=guest).status_code == 401
    assert client.get(f"/admin/bookings/{ref}/ticket", headers=guest).status_code == 401
    assert client.post(f"/bookings/{ref}/checkout", headers=guest).status_code == 200
    assert client.post(f"/bookings/{ref}/sandbox-pay", headers=guest).status_code == 200
    ticket = client.get(f"/bookings/{ref}/ticket", headers=guest)
    assert ticket.status_code == 200
    assert ticket.json()["booking"]["payment_status"] == "paid"
    assert ticket.json()["qr_data_url"].startswith("data:image/png;base64,")
    domain["module"].app.state.settings = settings


def test_guest_retries_create_one_booking(domain):
    client = domain["booking"]
    headers = {
        "Authorization": "Guest " + secrets.token_hex(32),
        "Idempotency-Key": uuid4().hex,
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda _: client.post("/bookings", json=command(), headers=headers),
                range(4),
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["reference"] for r in responses}) == 1
    changed = {**command(), "guest_count": 3}
    assert client.post("/bookings", json=changed, headers=headers).status_code == 409


@pytest.mark.parametrize(
    "authorization",
    ["Guest short", "Guest " + "g" * 64, "Guest " + "a" * 65, "Bearer invalid"],
)
def test_invalid_guest_or_account_access_is_rejected(domain, authorization):
    assert (
        domain["booking"]
        .post(
            "/bookings",
            json=command(),
            headers={"Authorization": authorization, "Idempotency-Key": uuid4().hex},
        )
        .status_code
        == 401
    )
