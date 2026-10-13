from wonderland_common.web import create_app
from .routes import router

app = create_app("booking-service", "booking")
from .payments import CircuitBreaker

app.state.payment_breaker = CircuitBreaker()
app.include_router(router)
settings = app.state.settings
logger = app.state.logger
from wonderland_common.web import SAFE_REQUEST_ID
