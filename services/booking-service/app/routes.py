import base64
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from io import BytesIO
import json
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import jwt
import qrcode
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import Identity, administrator, visitor
from wonderland_common.database import database
from . import payments

router = APIRouter()
PARK_TIMEZONE = ZoneInfo("Asia/Colombo")
Reference = Annotated[str, Path(pattern=r"^WL-[A-F0-9]{32}$")]
PUBLIC_COLUMNS = (
    "reference",
    "tier_id",
    "tier_name",
    "tier_revision",
    "guest_count",
    "visit_date",
    "time_slot",
    "amount_cents",
    "currency",
    "status",
    "payment_status",
    "created_at",
    "confirmed_at",
)


def public(row):
    return {key: row[key] for key in PUBLIC_COLUMNS}


def owned(conn, reference, identity, lock=False):
    row = (
        conn.execute(
            text(
                "SELECT * FROM booking.bookings WHERE reference=:reference AND owner_id=:owner"
                + (" FOR UPDATE" if lock else "")
            ),
            {"reference": reference, "owner": identity.subject},
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Booking not found")
    return dict(row)


class BookingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier_id: UUID
    guest_count: int = Field(ge=1, le=5, strict=True)
    visit_date: date
    time_slot: str = Field(pattern=r"^(09:00|12:00|15:00)$")


class PriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_cents: int = Field(gt=0, le=10000000, strict=True)


@router.get("/identity")
def identity_info(identity: Identity = Depends(visitor)):
    return {
        "subject": identity.subject,
        "role": identity.role,
        "mode": "local-development",
    }


@router.get("/ticket-tiers")
def tiers(engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT * FROM booking.ticket_tiers WHERE active ORDER BY max_guests"
                )
            ).mappings()
        ]


@router.patch("/ticket-tiers/{tier_id}", dependencies=[Depends(administrator)])
def update_price(tier_id: UUID, body: PriceUpdate, engine: Engine = Depends(database)):
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "UPDATE booking.ticket_tiers SET price_cents=:price,revision=revision+1,updated_at=now() WHERE id=:id RETURNING *"
                ),
                {"id": tier_id, "price": body.price_cents},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Ticket tier not found")
        return dict(row)


@router.post("/bookings", status_code=201)
def book(
    body: BookingCommand,
    response: Response,
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
            return public(existing)
        now = datetime.now(PARK_TIMEZONE)
        if body.visit_date < now.date() or body.visit_date > now.date() + timedelta(
            days=365
        ):
            raise HTTPException(422, "Visit date must be today through 365 days ahead")
        if body.visit_date == now.date() and body.time_slot <= now.strftime("%H:%M"):
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
        return public(row)


@router.get("/bookings")
def history(identity: Identity = Depends(visitor), engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            public(r)
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
        return public(owned(conn, reference, identity))


@router.post("/bookings/{reference}/checkout")
def checkout(
    reference: Reference,
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    settings = request.app.state.settings
    with engine.begin() as conn:
        booking = owned(conn, reference, identity, lock=True)
        if booking["status"] == "confirmed":
            raise HTTPException(409, "Booking is already paid")
        if booking["payment_session_id"]:
            return {
                "provider": booking["payment_provider"],
                "checkout_url": booking["checkout_url"],
                "reference": reference,
            }
        if settings.payment_provider == "local":
            if (
                settings.environment not in {"local", "test"}
                or not settings.local_webhook_secret
            ):
                raise HTTPException(503, "Local payment simulator is unavailable")
            session_id, url = "local_" + reference, None
        else:
            try:
                session = request.app.state.payment_breaker.call(
                    lambda: payments.create_stripe_checkout(settings, booking)
                )
            except stripe.StripeError:
                raise HTTPException(
                    503, "Test payment provider unavailable; booking remains pending"
                ) from None
            if session.livemode is not False or not session.id.startswith("cs_test_"):
                raise HTTPException(502, "Provider did not return a test checkout")
            if not session.url or not session.url.startswith(
                "https://checkout.stripe.com/"
            ):
                raise HTTPException(
                    502, "Provider did not return a valid test checkout URL"
                )
            session_id, url = session.id, session.url
        conn.execute(
            text(
                "UPDATE booking.bookings SET payment_provider=:provider,payment_session_id=:session,checkout_url=:url WHERE reference=:reference"
            ),
            {
                "provider": settings.payment_provider,
                "session": session_id,
                "url": url,
                "reference": reference,
            },
        )
        return {
            "provider": settings.payment_provider,
            "checkout_url": url,
            "reference": reference,
        }


def confirm(engine, notice):
    fingerprint = hashlib.sha256(notice.model_dump_json().encode()).hexdigest()
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM booking.bookings WHERE reference=:ref FOR UPDATE"),
                {"ref": notice.reference},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(400, "Payment does not match a pending checkout")
        if (
            row["payment_session_id"] != notice.session_id
            or row["payment_provider"] != notice.provider
            or row["amount_cents"] != notice.amount_cents
            or row["currency"].lower() != notice.currency
        ):
            raise HTTPException(
                400, "Payment does not match the stored checkout and price"
            )
        processed = conn.execute(
            text("""INSERT INTO booking.payment_events(provider,event_id,booking_reference,payload_hash)
            VALUES (:provider,:event,:ref,:hash) ON CONFLICT DO NOTHING RETURNING event_id"""),
            {
                "provider": notice.provider,
                "event": notice.event_id,
                "ref": notice.reference,
                "hash": fingerprint,
            },
        ).scalar()
        if processed is None:
            previous = conn.execute(
                text(
                    "SELECT payload_hash FROM booking.payment_events WHERE provider=:provider AND event_id=:event"
                ),
                {"provider": notice.provider, "event": notice.event_id},
            ).scalar_one()
            if previous != fingerprint:
                raise HTTPException(409, "Payment event identifier conflict")
            return {"received": True, "duplicate": True}
        if row["status"] == "confirmed":
            return {"received": True, "duplicate": True}
        conn.execute(
            text(
                "UPDATE booking.bookings SET status='confirmed',payment_status='paid',confirmed_at=now() WHERE reference=:ref"
            ),
            {"ref": notice.reference},
        )
        payload = {
            "booking_reference": notice.reference,
            "tier_id": str(row["tier_id"]),
            "tier_name": row["tier_name"],
            "guest_count": row["guest_count"],
            "amount_cents": row["amount_cents"],
            "currency": row["currency"],
        }
        conn.execute(
            text("""INSERT INTO booking.outbox(event_id,event_type,booking_reference,payload)
            VALUES (:id,'ticket.purchased',:ref,CAST(:payload AS jsonb))"""),
            {
                "id": "purchase:" + notice.reference,
                "ref": notice.reference,
                "payload": json.dumps(payload),
            },
        )
        return {"received": True, "duplicate": False}


@router.post("/payments/webhook")
async def webhook(request: Request, engine: Engine = Depends(database)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise HTTPException(413, "Webhook payload is too large")
    signature = request.headers.get(
        "Stripe-Signature"
        if request.app.state.settings.payment_provider == "stripe"
        else "X-Sandbox-Signature",
        "",
    )
    notice = payments.verify_notice(bytes(raw), signature, request.app.state.settings)
    return (
        await run_in_threadpool(confirm, engine, notice)
        if notice
        else {"received": True, "ignored": True}
    )


@router.post("/bookings/{reference}/sandbox-pay")
def sandbox_pay(
    reference: Reference,
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    settings = request.app.state.settings
    if (
        settings.payment_provider != "local"
        or settings.environment not in {"local", "test"}
        or not settings.local_webhook_secret
    ):
        raise HTTPException(404, "Local payment simulator is disabled")
    with engine.connect() as conn:
        booking = owned(conn, reference, identity)
    if booking["payment_provider"] != "local" or not booking["payment_session_id"]:
        raise HTTPException(409, "Create a local checkout first")
    event = {
        "id": "local_paid_" + reference,
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "id": booking["payment_session_id"],
                "metadata": {"booking_reference": reference},
                "amount_total": booking["amount_cents"],
                "currency": booking["currency"].lower(),
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }
    raw = json.dumps(event).encode()
    # Exercise the same signed-event verification and atomic confirmation path.
    signature = payments.local_signature(
        raw, settings.local_webhook_secret.get_secret_value()
    )
    return confirm(engine, payments.verify_notice(raw, signature, settings))


@router.get("/bookings/{reference}/ticket")
def ticket(
    reference: Reference,
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    with engine.connect() as conn:
        booking = owned(conn, reference, identity)
    if booking["status"] != "confirmed":
        raise HTTPException(409, "Tickets are available only after verified payment")
    secret = request.app.state.settings.ticket_secret
    if not secret:
        raise HTTPException(503, "Ticket signing is not configured")
    expires = datetime.combine(
        booking["visit_date"] + timedelta(days=1), time.min, PARK_TIMEZONE
    )
    token = jwt.encode(
        {
            "iss": "wonderland-tickets",
            "aud": "wonderland-gate",
            "kind": "ticket",
            "ref": reference,
            "iat": datetime.now(timezone.utc),
            "exp": expires,
        },
        secret.get_secret_value(),
        algorithm="HS256",
    )
    buffer = BytesIO()
    qrcode.make(token).save(buffer, format="PNG")
    return {
        "booking": public(booking),
        "ticket_token": token,
        "qr_data_url": "data:image/png;base64,"
        + base64.b64encode(buffer.getvalue()).decode(),
    }
