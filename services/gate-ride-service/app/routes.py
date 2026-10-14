from datetime import date, datetime
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import administrator, visitor, Identity
from wonderland_common.database import database
from wonderland_common.tickets import verify_ticket, owner_tag
from wonderland_common.resilience import CircuitBreaker

router = APIRouter()
admin = APIRouter(prefix="/admin", dependencies=[Depends(administrator)])
PARK_TZ = ZoneInfo("Asia/Colombo")


class CatalogLookup:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker()

    def get(self, attraction_id, request_id=None):
        def request():
            with httpx.Client(timeout=3, follow_redirects=False) as client:
                response = client.get(
                    f"{self.base_url}/attractions/{attraction_id}",
                    headers={"X-Request-ID": request_id} if request_id else {},
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                return response

        try:
            response = self.breaker.call(request)
            if response.status_code == 404:
                raise HTTPException(422, "Attraction is retired or unavailable")
            if response.status_code != 200:
                raise HTTPException(503, "Attraction status could not be verified")
            data = response.json()
            if (
                not isinstance(data, dict)
                or data.get("id") != str(attraction_id)
                or not isinstance(data.get("name"), str)
            ):
                raise ValueError("Invalid catalog response")
            if data.get("operational_status") != "open":
                raise HTTPException(422, "Attraction is not operational")
            if not 1 <= len(data["name"]) <= 120:
                raise ValueError("Invalid attraction name")
            return data
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                503, "Attractions service unavailable; ride event was not recorded"
            ) from None


class Scan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_token: SecretStr = Field(min_length=1, max_length=8192)


class Arrival(Scan):
    guest_count: int = Field(ge=1, le=5, strict=True)


class Ride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    booking_reference: str = Field(pattern=r"^WL-[A-F0-9]{32}$")
    attraction_id: UUID
    guest_count: int = Field(ge=1, le=5, strict=True)


@admin.post("/tickets/validate")
def validate(body: Scan, request: Request, engine: Engine = Depends(database)):
    claims = verify_ticket(
        body.ticket_token.get_secret_value(), request.app.state.settings
    )
    with engine.connect() as conn:
        checked = conn.execute(
            text("SELECT 1 FROM visits.check_ins WHERE booking_reference=:ref"),
            {"ref": claims.ref},
        ).scalar()
    return {
        "reference": claims.ref,
        "visit_date": claims.visit_date,
        "guest_count": claims.guest_count,
        "already_checked_in": bool(checked),
    }


@admin.post("/check-ins", status_code=201)
def check_in(body: Arrival, request: Request, engine: Engine = Depends(database)):
    claims = verify_ticket(
        body.ticket_token.get_secret_value(), request.app.state.settings
    )
    if body.guest_count != claims.guest_count:
        raise HTTPException(
            422, "This implementation admits the full booked party in one check-in"
        )
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("""INSERT INTO visits.check_ins(booking_reference,owner_tag,guest_count,visit_date)
            VALUES (:ref,:owner,:guests,:day) ON CONFLICT DO NOTHING
            RETURNING booking_reference,guest_count,visit_date,checked_in_at"""),
                {
                    "ref": claims.ref,
                    "owner": claims.owner_tag,
                    "guests": claims.guest_count,
                    "day": claims.visit_date,
                },
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(409, "This booking has already checked in")
        payload = {
            "booking_reference": claims.ref,
            "guest_count": claims.guest_count,
            "visit_date": claims.visit_date.isoformat(),
        }
        conn.execute(
            text(
                "INSERT INTO visits.outbox(event_id,event_type,payload) VALUES (:id,'visitor.arrived',CAST(:payload AS jsonb))"
            ),
            {"id": "arrival:" + claims.ref, "payload": json.dumps(payload)},
        )
        return dict(row)


@admin.post("/ride-events", status_code=201)
def record_ride(body: Ride, request: Request, engine: Engine = Depends(database)):
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    with engine.connect() as conn:
        existing = (
            conn.execute(
                text("SELECT * FROM visits.ride_events WHERE event_id=:id"),
                {"id": body.event_id},
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["request_hash"] != fingerprint:
                raise HTTPException(
                    409, "Ride event ID was reused with different input"
                )
            return {"event_id": body.event_id, "duplicate": True}
        arrival = (
            conn.execute(
                text(
                    "SELECT guest_count,visit_date FROM visits.check_ins WHERE booking_reference=:ref"
                ),
                {"ref": body.booking_reference},
            )
            .mappings()
            .first()
        )
    if not arrival:
        raise HTTPException(422, "Check in this booking before recording a ride")
    if arrival["visit_date"] != datetime.now(PARK_TZ).date():
        raise HTTPException(422, "Ride usage must be recorded on the visit date")
    if body.guest_count > arrival["guest_count"]:
        raise HTTPException(422, "Ride guests exceed the checked-in party")
    attraction = request.app.state.catalog.get(
        body.attraction_id, request_id=request.state.request_id
    )
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("""INSERT INTO visits.ride_events(event_id,booking_reference,attraction_id,attraction_name,guest_count,request_hash)
            VALUES (:id,:ref,:attraction,:name,:guests,:hash) ON CONFLICT DO NOTHING RETURNING event_id,occurred_at"""),
                {
                    "id": body.event_id,
                    "ref": body.booking_reference,
                    "attraction": body.attraction_id,
                    "name": attraction["name"],
                    "guests": body.guest_count,
                    "hash": fingerprint,
                },
            )
            .mappings()
            .first()
        )
        if not row:
            old = conn.execute(
                text("SELECT request_hash FROM visits.ride_events WHERE event_id=:id"),
                {"id": body.event_id},
            ).scalar_one()
            if old != fingerprint:
                raise HTTPException(
                    409, "Ride event ID was reused with different input"
                )
            return {"event_id": body.event_id, "duplicate": True}
        payload = {
            "booking_reference": body.booking_reference,
            "attraction_id": str(body.attraction_id),
            "attraction_name": attraction["name"],
            "guest_count": body.guest_count,
        }
        conn.execute(
            text(
                "INSERT INTO visits.outbox(event_id,event_type,payload) VALUES (:id,'ride.used',CAST(:payload AS jsonb))"
            ),
            {"id": "ride:" + str(body.event_id), "payload": json.dumps(payload)},
        )
        return {**dict(row), "duplicate": False}


@admin.get("/activity")
def activity(visit_date: date | None = None, engine: Engine = Depends(database)):
    day = visit_date or datetime.now(PARK_TZ).date()
    with engine.connect() as conn:
        arrivals = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT booking_reference,guest_count,visit_date,checked_in_at FROM visits.check_ins WHERE (checked_in_at AT TIME ZONE 'Asia/Colombo')::date=:day ORDER BY checked_in_at DESC LIMIT 200"
                ),
                {"day": day},
            ).mappings()
        ]
        totals = (
            conn.execute(
                text(
                    "SELECT count(*) AS bookings,coalesce(sum(guest_count),0) AS guests FROM visits.check_ins WHERE (checked_in_at AT TIME ZONE 'Asia/Colombo')::date=:day"
                ),
                {"day": day},
            )
            .mappings()
            .one()
        )
        rides = [
            dict(r)
            for r in conn.execute(
                text("""SELECT attraction_id,(array_agg(attraction_name ORDER BY occurred_at DESC))[1] AS attraction_name,count(*) AS ride_events,sum(guest_count) AS riders
            FROM visits.ride_events WHERE (occurred_at AT TIME ZONE 'Asia/Colombo')::date=:day
            GROUP BY attraction_id ORDER BY riders DESC"""),
                {"day": day},
            ).mappings()
        ]
    return {
        "visit_date": day,
        "arrivals": arrivals,
        "arrival_bookings": totals["bookings"],
        "arriving_guests": totals["guests"],
        "rides": rides,
    }


@router.get("/visits")
def history(
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    tag = owner_tag(identity.subject, request.app.state.settings)
    with engine.connect() as conn:
        visits = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT booking_reference,guest_count,visit_date,checked_in_at FROM visits.check_ins WHERE owner_tag=:tag ORDER BY checked_in_at DESC LIMIT 100"
                ),
                {"tag": tag},
            ).mappings()
        ]
        rides = [
            dict(r)
            for r in conn.execute(
                text("""SELECT r.event_id,r.booking_reference,r.attraction_id,r.attraction_name,r.guest_count,r.occurred_at
            FROM visits.ride_events r JOIN visits.check_ins v USING(booking_reference)
            WHERE v.owner_tag=:tag ORDER BY r.occurred_at DESC LIMIT 1000"""),
                {"tag": tag},
            ).mappings()
        ]
    return {"visits": visits, "ride_events": rides}


router.include_router(admin)
