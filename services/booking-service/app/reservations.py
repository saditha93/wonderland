"""Reservations API routes for the booking service."""

from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import Identity, visitor
from wonderland_common.database import database


from .booking_store import PARK_TIMEZONE, Reference, public_booking, find_owned_booking

router = APIRouter()


class BookingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier_id: UUID
    guest_count: int = Field(ge=1, le=5, strict=True)
    visit_date: date
    time_slot: str = Field(pattern=r"^(09:00|12:00|15:00)$")


@router.post("/bookings", status_code=201)
def book(
    body: BookingCommand,
    response: Response,
    request: Request,
    idempotency_key: Annotated[str, Header(pattern=r"^[A-Za-z0-9_-]{8,80}$")],
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    command = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(command, sort_keys=True).encode()
    ).hexdigest()
    with engine.begin() as conn:
        # Read existing commands first: a valid retry must not change after price/date updates.
        existing = (
            conn.execute(
                text(
                    "SELECT * FROM booking.bookings WHERE owner_id=:owner AND idempotency_key=:key"
                ),
                {"owner": identity.subject, "key": idempotency_key},
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["request_hash"] != fingerprint:
                raise HTTPException(409, "Idempotency key was used for another request")
            response.status_code = 200
            return public_booking(existing)
        now = datetime.now(PARK_TIMEZONE)
        if body.visit_date < now.date() or body.visit_date > now.date() + timedelta(
            days=365
        ):
            raise HTTPException(422, "Visit date must be today through 365 days ahead")
        if (
            not request.app.state.settings.demo_mode
            and body.visit_date == now.date()
            and body.time_slot <= now.strftime("%H:%M")
        ):
            raise HTTPException(422, "Choose a future time slot")
        tier = (
            conn.execute(
                text(
                    "SELECT * FROM booking.ticket_tiers WHERE id=:id AND active FOR SHARE"
                ),
                {"id": body.tier_id},
            )
            .mappings()
            .first()
        )
        if not tier:
            raise HTTPException(422, "Ticket tier is unavailable")
        if not tier["min_guests"] <= body.guest_count <= tier["max_guests"]:
            raise HTTPException(
                422, "Guest count is outside this tier's permitted range"
            )
        row = (
            conn.execute(
                text("""INSERT INTO booking.bookings
            (reference,owner_id,tier_id,tier_name,tier_revision,guest_count,visit_date,time_slot,amount_cents,currency,idempotency_key,request_hash)
            VALUES (:reference,:owner,:tier_id,:tier_name,:revision,:guests,:visit_date,:slot,:amount,:currency,:key,:hash)
            ON CONFLICT (owner_id,idempotency_key) DO NOTHING RETURNING *"""),
                {
                    "reference": "WL-" + uuid4().hex.upper(),
                    "owner": identity.subject,
                    "tier_id": body.tier_id,
                    "tier_name": tier["name"],
                    "revision": tier["revision"],
                    "guests": body.guest_count,
                    "visit_date": body.visit_date,
                    "slot": body.time_slot,
                    "amount": tier["price_cents"],
                    "currency": tier["currency"],
                    "key": idempotency_key,
                    "hash": fingerprint,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM booking.bookings WHERE owner_id=:owner AND idempotency_key=:key"
                    ),
                    {"owner": identity.subject, "key": idempotency_key},
                )
                .mappings()
                .one()
            )
            if row["request_hash"] != fingerprint:
                raise HTTPException(409, "Idempotency key was used for another request")
            response.status_code = 200
        return public_booking(row)


@router.get("/bookings")
def history(identity: Identity = Depends(visitor), engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            public_booking(r)
            for r in conn.execute(
                text(
                    "SELECT * FROM booking.bookings WHERE owner_id=:owner ORDER BY created_at DESC LIMIT 100"
                ),
                {"owner": identity.subject},
            ).mappings()
        ]


@router.get("/bookings/{reference}")
def get_booking(
    reference: Reference,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    with engine.connect() as conn:
        return public_booking(find_owned_booking(conn, reference, identity))
