import json
import logging
import re
import sys
from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .config import Settings
from .database import create_database

SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def create_app(service: str, schema: str) -> FastAPI:
    settings = Settings()
    app = FastAPI(title=f"Wonderland {service}", version=settings.version)
    app.state.settings = settings
    app.state.engine = create_database(settings)
    logger = logging.getLogger(service)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    app.state.logger = logger

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, exc):
        # Never serialize SQL, bound values, credentials, or exception text.
        return JSONResponse(
            {"detail": "Database operation unavailable"}, status_code=503
        )

    @app.middleware("http")
    async def context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if SAFE_REQUEST_ID.fullmatch(incoming) else str(uuid4())
        request.state.request_id = request_id
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            if request.url.path not in {"/health", "/health/live", "/health/ready"}:
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "service": service,
                        "request_id": request_id,
                        "method": request.method,
                        "route": getattr(
                            request.scope.get("route"), "path", "unmatched"
                        ),
                        "status": status,
                        "duration_ms": round((perf_counter() - started) * 1000, 3),
                    }
                )
            )

    def health(scope):
        return {
            "service": service,
            "status": "ok",
            "version": settings.version,
            "environment": settings.environment,
            "scope": scope,
        }

    @app.get("/health")
    @app.get("/health/live")
    def live():
        return health("process")

    @app.get("/health/ready")
    def ready():
        engine = app.state.engine
        if engine is None:
            return JSONResponse(
                {**health("database"), "status": "unavailable"}, status_code=503
            )
        try:
            with engine.connect() as conn:
                revision = conn.execute(
                    text(f"SELECT max(version) FROM {schema}.schema_migrations")
                ).scalar()
                if revision != 1:
                    raise ValueError("Migration required")
        except (SQLAlchemyError, ValueError):
            return JSONResponse(
                {**health("database"), "status": "unavailable"}, status_code=503
            )
        return health("database")

    return app
