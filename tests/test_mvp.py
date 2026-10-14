"""MVP convenience must preserve ownership, payment and date boundaries."""

from datetime import datetime, timedelta
import importlib
from uuid import UUID
from zoneinfo import ZoneInfo

import jwt
import pytest

from test_domain import command, create
from test_phase3 import phase3, paid_today
from wonderland_common.config import Settings


def test_reference_check_in_preserves_visitor_ownership(phase3):
    original = paid_today(phase3, subject="booking-owner")
    ref = original["booking"]["reference"]
    client = phase3["booking"]
    path = f"/admin/bookings/{ref}/ticket"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=phase3["headers"]("other-visitor")).status_code == 403
    response = client.get(path, headers=phase3["headers"]("staff", "admin"))
    assert response.status_code == 200
    ticket = response.json()
    def claims(value):
        return jwt.decode(value, phase3["public"], algorithms=["RS256"], audience="wonderland-gate", issuer="wonderland-tickets")
    assert claims(ticket["ticket_token"])["owner_tag"] == claims(original["ticket_token"])["owner_tag"]
    headers = phase3["headers"]("staff", "admin")
    body = {"ticket_token": ticket["ticket_token"], "guest_count": 4}
    assert phase3["gate"].post("/admin/check-ins", headers=headers, json=body).status_code == 201
    assert phase3["gate"].post("/admin/check-ins", headers=headers, json=body).status_code == 409
    visits = phase3["gate"].get("/visits", headers=phase3["headers"]("booking-owner"))
    assert visits.status_code == 200
    assert visits.json()["visits"][0]["booking_reference"] == ref


def test_reference_lookup_requires_confirmed_payment(domain):
    ref = create(domain).json()["reference"]
    headers = domain["headers"]("staff", "admin")
    client = domain["booking"]
    assert client.get(f"/admin/bookings/{ref}/ticket", headers=headers).status_code == 409
    assert client.get("/admin/bookings/WL-" + "0" * 32 + "/ticket", headers=headers).status_code == 404


def test_demo_can_book_today_after_slots_but_rejects_invalid_dates(domain, monkeypatch):
    routes = importlib.import_module(domain["module"].__package__ + ".routes")
    today = datetime.now(ZoneInfo("Asia/Colombo")).date()
    class Evening(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.combine(today, cls.min.time(), ZoneInfo("Asia/Colombo")).replace(hour=20).astimezone(tz)
    monkeypatch.setattr(routes, "datetime", Evening)
    body = command(visit_date=today.isoformat(), time_slot="09:00")
    assert create(domain, body=body).status_code == 422
    domain["module"].settings.demo_mode = True
    assert create(domain, body=body).status_code == 201
    for invalid in (today - timedelta(days=1), today + timedelta(days=366)):
        assert create(domain, body=command(visit_date=invalid.isoformat())).status_code == 422
    assert create(domain, body=command(guests=5, visit_date=today.isoformat())).status_code == 422


def test_demo_mode_is_prohibited_in_cloud(monkeypatch):
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Demo mode requires"):
        Settings(environment="aws", auth_mode="disabled", demo_mode=True)
