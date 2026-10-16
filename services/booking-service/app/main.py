"""Booking API assembly: routes, login and readiness dependencies."""

from fastapi import HTTPException
from wonderland_common.local_login import configure_login
from wonderland_common.resilience import CircuitBreaker
from wonderland_common.tickets import signing_key
from wonderland_common.web import create_app
from .routes import router

app = create_app("booking-service", "booking", revision=2)
app.state.payment_breaker = CircuitBreaker()
app.include_router(router)
configure_login(app)
settings = app.state.settings
logger = app.state.logger


def booking_readiness():
    """A booking API is ready only when it can issue valid tickets."""
    signing_key(settings)
    if not settings.ticket_owner_secret:
        raise HTTPException(503, "Ticket ownership key is not configured")


app.state.readiness_check = booking_readiness
