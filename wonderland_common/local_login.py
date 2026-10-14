"""Password sign-in for explicitly configured local/test accounts only."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from threading import Lock
from time import monotonic
from typing import Literal

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return f"{salt}:{digest.hex()}"


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=8, max_length=256)
    portal: Literal["visitor", "admin"]


router = APIRouter()


@router.post("/auth/local-login")
def login(body: Login, request: Request):
    settings = request.app.state.settings
    if settings.environment not in {"local", "test"} or settings.auth_mode != "local":
        raise HTTPException(404, "Not found")
    if not settings.local_accounts_json:
        raise HTTPException(503, "Local accounts are not configured. Run local setup and restart the APIs.")
    # Bound password hashing work, including successful attempts. Process-local by
    # design: this endpoint is for local demos, never distributed cloud identity.
    with request.app.state.local_login_lock:
        now = monotonic()
        attempts = [t for t in request.app.state.local_login_attempts if now - t < 60]
        if len(attempts) >= 20:
            raise HTTPException(429, "Too many sign-in attempts. Wait a minute and try again.", headers={"Retry-After": "60"})
        request.app.state.local_login_attempts = [*attempts, now]
    accounts = json.loads(settings.local_accounts_json.get_secret_value())
    account = accounts.get(body.email.strip().lower())
    # Unknown accounts also perform the expensive hash; no account enumeration.
    encoded = account["password_hash"] if account else "0" * 32 + ":" + "0" * 128
    salt = encoded.split(":", 1)[0]
    matches = hmac.compare_digest(password_hash(body.password.get_secret_value(), salt), encoded)
    if not account or not matches or account["role"] != body.portal:
        raise HTTPException(401, "Email or password is incorrect for this portal")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"iss": "wonderland-local", "aud": "wonderland-local", "sub": account["subject"],
         "role": account["role"], "kind": "access", "iat": now, "exp": now + timedelta(hours=1)},
        settings.auth_secret.get_secret_value(), algorithm="HS256",
    )
    return {"access_token": token}


def configure_login(app):
    app.state.local_login_lock = Lock()
    app.state.local_login_attempts = []
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == "/auth/local-login":
            return JSONResponse({"detail": "Check your sign-in details"}, status_code=422)
        return await request_validation_exception_handler(request, exc)
