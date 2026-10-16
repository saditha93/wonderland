"""Gate API assembly and independent ticket-verification readiness."""

from fastapi import HTTPException
from wonderland_common.tickets import verification_key
from wonderland_common.web import create_app
from .routes import CatalogLookup, router

app = create_app("gate-ride-service", "visits")
app.state.catalog = CatalogLookup(
    app.state.settings.attractions_url, app.state.settings.internal_ca_path
)
app.include_router(router)
settings = app.state.settings
logger = app.state.logger


def gate_readiness():
    """Admission requires a usable public key and ownership key."""
    verification_key(settings)
    if not settings.ticket_owner_secret:
        raise HTTPException(503, "Ticket ownership key is not configured")


app.state.readiness_check = gate_readiness
