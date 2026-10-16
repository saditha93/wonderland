"""Checkout API routes for the booking service."""

import hashlib
import json

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import Identity, visitor
from wonderland_common.database import database
from . import payments


from .booking_store import Reference, find_owned_booking

router = APIRouter()


@router.post("/bookings/{reference}/checkout")
def checkout(
    reference: Reference,
    request: Request,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    settings = request.app.state.settings
    with engine.begin() as conn:
        booking = find_owned_booking(conn, reference, identity, lock=True)
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


def confirm_payment(engine, notice):
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
        await run_in_threadpool(confirm_payment, engine, notice)
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
        booking = find_owned_booking(conn, reference, identity)
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
    return confirm_payment(engine, payments.verify_notice(raw, signature, settings))
