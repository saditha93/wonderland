"""Independent gate verification with public key; never use access tokens as tickets."""

from datetime import date, datetime, time, timedelta
import hashlib
import base64
import hmac
import re
from zoneinfo import ZoneInfo
import jwt
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PARK_TZ = ZoneInfo("Asia/Colombo")


class TicketClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ref: str = Field(pattern=r"^WL-[A-F0-9]{32}$")
    visit_date: date
    guest_count: int = Field(ge=1, le=5, strict=True)
    owner_tag: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: str


def owner_tag(subject, settings):
    if not settings.ticket_owner_secret:
        raise HTTPException(503, "Ticket ownership key is not configured")
    return hmac.new(
        settings.ticket_owner_secret.get_secret_value().encode(),
        subject.encode(),
        hashlib.sha256,
    ).hexdigest()


def verification_key(settings):
    if not settings.ticket_public_key_path and not settings.ticket_public_key_b64:
        raise HTTPException(503, "Gate ticket verification key is not configured")
    try:
        key = (
            base64.b64decode(settings.ticket_public_key_b64).decode()
            if settings.ticket_public_key_b64
            else settings.ticket_public_key_path.read_text()
        )
    except (OSError, ValueError, UnicodeError):
        raise HTTPException(
            503, "Gate ticket verification key is unavailable"
        ) from None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    try:
        parsed = serialization.load_pem_public_key(key.encode())
        if not isinstance(parsed, rsa.RSAPublicKey) or parsed.key_size < 2048:
            raise ValueError("Invalid gate key")
    except (ValueError, TypeError):
        raise HTTPException(503, "Gate ticket verification key is invalid") from None
    return parsed


def verify_ticket(token, settings, today=None):
    key = verification_key(settings)
    try:
        raw = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience="wonderland-gate",
            issuer="wonderland-tickets",
            options={
                "require": [
                    "iat",
                    "exp",
                    "ref",
                    "visit_date",
                    "guest_count",
                    "owner_tag",
                    "kind",
                ]
            },
        )
        claims = TicketClaims.model_validate(raw)
        if claims.kind != "ticket":
            raise ValueError("Not a ticket")
        if claims.visit_date != (today or datetime.now(PARK_TZ).date()):
            raise HTTPException(422, "Ticket is valid only on its visit date")
        expected = datetime.combine(
            claims.visit_date + timedelta(days=1), time.min, PARK_TZ
        ).timestamp()
        if raw["exp"] != expected:
            raise ValueError("Unexpected ticket validity")
        return claims
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, ValidationError, ValueError, TypeError):
        raise HTTPException(
            400, "Invalid, expired or legacy ticket; obtain a current digital ticket"
        ) from None


def signing_key(settings):
    if not settings.ticket_private_key_b64 and not settings.ticket_private_key_path:
        raise HTTPException(503, "Ticket signing key is not configured")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    try:
        pem = (
            base64.b64decode(settings.ticket_private_key_b64.get_secret_value())
            if settings.ticket_private_key_b64
            else settings.ticket_private_key_path.read_bytes()
        )
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("Invalid signing key")
        return key
    except (OSError, ValueError, TypeError):
        raise HTTPException(
            503, "Ticket signing key is unavailable or invalid"
        ) from None
