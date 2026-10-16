"""Tickets API routes for the booking service."""

import base64
from datetime import datetime, time, timedelta, timezone
from io import BytesIO

import jwt
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import Identity, administrator, visitor
from wonderland_common.database import database


from .booking_store import PARK_TIMEZONE, Reference, public_booking, find_owned_booking

router = APIRouter()


@router.get("/bookings/{reference}/ticket")
def ticket(
    reference: Reference,
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    with engine.connect() as conn:
        booking = find_owned_booking(conn, reference, identity)
    return issue_signed_ticket(booking, request.app.state.settings)


@router.get("/admin/bookings/{reference}/ticket", dependencies=[Depends(administrator)])
def staff_ticket(
    reference: Reference, request: Request, engine: Engine = Depends(database)
):
    """Resolve a presented reference to its signed ticket for gate staff."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM booking.bookings WHERE reference=:reference"),
                {"reference": reference},
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(404, "Booking not found")
    return issue_signed_ticket(dict(row), request.app.state.settings)


def issue_signed_ticket(booking, settings):
    if booking["status"] != "confirmed":
        raise HTTPException(409, "Tickets are available only after verified payment")
    from wonderland_common.tickets import owner_tag, signing_key

    private_key = signing_key(settings)
    extra = {
        "visit_date": booking["visit_date"].isoformat(),
        "guest_count": booking["guest_count"],
        "owner_tag": owner_tag(booking["owner_id"], settings),
    }
    expires = datetime.combine(
        booking["visit_date"] + timedelta(days=1), time.min, PARK_TIMEZONE
    )
    token = jwt.encode(
        {
            "iss": "wonderland-tickets",
            "aud": "wonderland-gate",
            "kind": "ticket",
            "ref": booking["reference"],
            "iat": datetime.now(timezone.utc),
            "exp": expires,
            **extra,
        },
        private_key,
        algorithm="RS256",
    )
    buffer = BytesIO()
    qrcode.make(token).save(buffer, format="PNG")
    return {
        "booking": public_booking(booking),
        "ticket_token": token,
        "qr_data_url": "data:image/png;base64,"
        + base64.b64encode(buffer.getvalue()).decode(),
    }
