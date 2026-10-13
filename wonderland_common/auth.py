from dataclasses import dataclass
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    subject: str
    role: str


def visitor(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> Identity:
    settings = request.app.state.settings
    if settings.auth_mode != "local" or settings.environment not in {"local", "test"}:
        raise HTTPException(
            503, "Authentication is not configured; Cognito integration is Phase 3"
        )
    if not credentials:
        raise HTTPException(
            401,
            "A signed local development access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.auth_secret.get_secret_value(),
            algorithms=["HS256"],
            audience="wonderland-local",
            issuer="wonderland-local",
            options={"require": ["sub", "exp", "iat", "role", "kind"]},
        )
        if (
            claims["kind"] != "access"
            or claims["role"] not in {"visitor", "admin"}
            or not claims["sub"]
        ):
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        raise HTTPException(
            401,
            "Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return Identity(claims["sub"], claims["role"])


def administrator(identity: Identity = Depends(visitor)) -> Identity:
    if identity.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return identity
