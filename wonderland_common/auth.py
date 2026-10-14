from dataclasses import dataclass
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    subject: str
    role: str
    mode: str = "local-development"


def visitor(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> Identity:
    settings = request.app.state.settings
    if settings.auth_mode == "disabled":
        raise HTTPException(503, "Authentication is not configured")
    if not credentials:
        raise HTTPException(
            401,
            "A valid access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if len(token) > 8192:
        raise HTTPException(401, "Invalid access token")
    try:
        if settings.auth_mode == "local":
            if settings.environment not in {"local", "test"}:
                raise HTTPException(503, "Local identity is disabled")
            claims = jwt.decode(
                token,
                settings.auth_secret.get_secret_value(),
                algorithms=["HS256"],
                audience="wonderland-local",
                issuer="wonderland-local",
                options={"require": ["sub", "exp", "iat", "role", "kind"]},
            )
            if claims["kind"] != "access" or claims["role"] not in {"visitor", "admin"}:
                raise jwt.InvalidTokenError()
            role, mode = claims["role"], "local-development"
        else:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 200
            ):
                raise jwt.InvalidTokenError()
            key = request.app.state.jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=settings.cognito_issuer,
                audience=settings.cognito_audience,
                options={
                    "verify_aud": settings.cognito_audience is not None,
                    "require": [
                        "sub",
                        "exp",
                        "iat",
                        "client_id",
                        "token_use",
                        "username",
                    ],
                },
            )
            if (
                claims["token_use"] != "access"
                or claims["client_id"] != settings.cognito_client_id
            ):
                raise jwt.InvalidTokenError()
            groups = claims.get("cognito:groups", [])
            if not isinstance(groups, list) or any(
                not isinstance(group, str) for group in groups
            ):
                raise jwt.InvalidTokenError()
            role = "admin" if settings.cognito_admin_group in groups else "visitor"
            mode = "cognito"
        if not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 160:
            raise jwt.InvalidTokenError()
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(
            503, "Identity signing keys are temporarily unavailable"
        ) from None
    except (jwt.InvalidTokenError, jwt.PyJWKClientError):
        raise HTTPException(
            401,
            "Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return Identity(claims["sub"], role, mode)


def administrator(identity: Identity = Depends(visitor)) -> Identity:
    if identity.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return identity
