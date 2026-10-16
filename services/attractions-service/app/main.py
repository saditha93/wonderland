"""Assemble the public catalogue and administrator attraction routes."""

from wonderland_common.web import create_app
from .routes import router

app = create_app("attractions-service", "attractions")
app.include_router(router)
settings = app.state.settings
logger = app.state.logger
