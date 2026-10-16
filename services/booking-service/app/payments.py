"""Test-only payment adapters. No production Stripe keys or live events accepted."""

import hashlib
import hmac
import json
from threading import Lock
from time import monotonic, time

import stripe
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError


from wonderland_common.resilience import CircuitBreaker


def create_stripe_checkout(settings, booking):
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe test mode is not configured")
    client = stripe.StripeClient(
        settings.stripe_secret_key.get_secret_value(),
        http_client=stripe.RequestsClient(timeout=5),
        max_network_retries=1,
    )
    return client.v1.checkout.sessions.create(
        {
            "mode": "payment",
            "client_reference_id": booking["reference"],
            "metadata": {"booking_reference": booking["reference"]},
            "line_items": [
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": booking["amount_cents"],
                        "product_data": {
                            "name": f"Wonderland {booking['tier_name']} ticket"
                        },
                    },
                    "quantity": 1,
                }
            ],
            "success_url": f"{settings.frontend_url}/?booking={booking['reference']}&payment=returned",
            "cancel_url": f"{settings.frontend_url}/?booking={booking['reference']}&payment=cancelled",
        },
        options={"idempotency_key": f"checkout-{booking['reference']}"},
    )


class PaymentNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    event_id: str = Field(min_length=1, max_length=200)
    reference: str = Field(pattern=r"^WL-[A-F0-9]{32}$")
    session_id: str = Field(min_length=1, max_length=200)
    amount_cents: StrictInt = Field(gt=0)
    currency: str


def local_signature(raw: bytes, secret: str, timestamp=None):
    timestamp = int(time()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_notice(raw: bytes, signature: str, settings):
    try:
        if settings.payment_provider == "stripe":
            if not settings.stripe_webhook_secret:
                raise HTTPException(503, "Stripe webhook secret is not configured")
            event = stripe.Webhook.construct_event(
                raw,
                signature,
                settings.stripe_webhook_secret.get_secret_value(),
                tolerance=300,
            ).to_dict()
            provider = "stripe"
        else:
            if (
                settings.environment not in {"local", "test"}
                or not settings.local_webhook_secret
            ):
                raise HTTPException(503, "Local payment simulator is unavailable")
            parts = dict(item.split("=", 1) for item in signature.split(","))
            timestamp = int(parts["t"])
            expected = local_signature(
                raw, settings.local_webhook_secret.get_secret_value(), timestamp
            ).split("v1=", 1)[1]
            if abs(time() - timestamp) > 300 or not hmac.compare_digest(
                parts["v1"], expected
            ):
                raise ValueError("Invalid local signature")
            event = json.loads(raw)
            provider = "local"
        if not isinstance(event, dict):
            raise ValueError("Expected an event object")
        # Missing livemode is also rejected: no ambiguous event may confirm payment.
        if event.get("livemode") is not False:
            raise ValueError("Live payment events are forbidden")
        if event.get("type") not in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }:
            return None
        session = event["data"]["object"]
        if session["payment_status"] != "paid" or session["status"] != "complete":
            return None
        return PaymentNotice(
            provider=provider,
            event_id=event["id"],
            reference=session["metadata"]["booking_reference"],
            session_id=session["id"],
            amount_cents=session["amount_total"],
            currency=session["currency"],
        )
    except HTTPException:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        ValidationError,
        stripe.SignatureVerificationError,
    ):
        raise HTTPException(400, "Invalid test payment event or signature") from None
