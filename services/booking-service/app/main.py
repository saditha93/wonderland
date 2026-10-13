"""Health-only foundation. No business routes or event consumption yet."""
import json
import logging
import re
import sys
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")
    environment: str = "local"
    version: str = "0.1.0"


settings = Settings()
SERVICE_NAME = "booking-service"
logger = logging.getLogger(SERVICE_NAME)
# Application logs are JSON on stdout; exclude raw URLs, headers and bodies.
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(message)s"))
logger.handlers = [handler]
logger.setLevel(logging.INFO)
logger.propagate = False
app = FastAPI(title=f"Wonderland {SERVICE_NAME}", version=settings.version)
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class Health(BaseModel):
    service: str
    status: str
    version: str
    environment: str
    scope: str


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if SAFE_REQUEST_ID.fullmatch(incoming) else str(uuid4())
    request.state.request_id = request_id
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        logger.info(json.dumps({
            "event": "http_request", "service": SERVICE_NAME,
            "request_id": request_id, "method": request.method,
            "route": getattr(route, "path", "unmatched"),
            "status": status, "duration_ms": round((perf_counter()-started)*1000, 3),
        }))


def health(scope: str) -> Health:
    return Health(service=SERVICE_NAME, status="ok", version=settings.version,
                  environment=settings.environment, scope=scope)


@app.get("/health", response_model=Health)
def summary():
    return health("skeleton-only")


@app.get("/health/live", response_model=Health)
def live():
    return health("process")


@app.get("/health/ready", response_model=Health)
def ready():
    # No business dependencies exist yet. Add actual dependency checks in P2/P4.
    return health("skeleton-only")
