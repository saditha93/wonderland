from wonderland_common.web import create_app
from .routes import router

app = create_app("attractions-service", "attractions")
app.include_router(router)
settings = app.state.settings
logger = app.state.logger
from wonderland_common.web import SAFE_REQUEST_ID
