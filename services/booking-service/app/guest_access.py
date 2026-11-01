"""Booking-only guest access using a private random browser-tab credential."""

import hashlib
import re

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from wonderland_common.auth import Identity, bearer, visitor


def booking_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Identity:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "guest":
        return visitor(request, credentials)
    if request.app.state.settings.auth_mode == "disabled":
        raise HTTPException(503, "Authentication is not configured")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise HTTPException(401, "Invalid guest booking access")
    # Only the digest is stored as the owner. A reference never grants access.
    subject = "guest:" + hashlib.sha256(token.encode()).hexdigest()
    return Identity(subject, "visitor", "guest")
