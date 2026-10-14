from wonderland_common.web import create_app
from .routes import router

app = create_app("booking-service", "booking", revision=2)
from .payments import CircuitBreaker

app.state.payment_breaker = CircuitBreaker()
app.include_router(router)
settings = app.state.settings
logger = app.state.logger
from wonderland_common.web import SAFE_REQUEST_ID

from wonderland_common.tickets import signing_key
from fastapi import HTTPException


def booking_readiness():
    signing_key(settings)
    if not settings.ticket_owner_secret:
        raise HTTPException(503, "Ticket ownership key is not configured")


app.state.readiness_check = booking_readiness
