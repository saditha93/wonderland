import importlib.util
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

from dotenv import load_dotenv
import jwt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "secrets/local.env")


def load_service(name):
    package_name = "testapp_" + uuid4().hex
    directory = ROOT / "services" / name / "app"
    spec = importlib.util.spec_from_file_location(
        package_name,
        directory / "__init__.py",
        submodule_search_locations=[str(directory)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    spec = importlib.util.spec_from_file_location(
        package_name + ".main", directory / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name + ".main"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def postgres_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL missing: real PostgreSQL integration tests not run"
        )
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail(
            "Refusing destructive integration fixtures outside a dedicated *_test database"
        )
    engine = create_engine(url, pool_size=10, max_overflow=10)
    from scripts.db_migrate import migrate

    migrate(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def domain(postgres_engine, monkeypatch):
    from scripts.db_migrate import seed

    with postgres_engine.begin() as conn:
        conn.exec_driver_sql(
            "TRUNCATE booking.outbox,booking.payment_events,booking.bookings,booking.ticket_tiers,attractions.attractions CASCADE"
        )
    seed(postgres_engine)
    for key, value in {
        "APP_DATABASE_URL": postgres_engine.url.render_as_string(hide_password=False),
        "APP_ENVIRONMENT": "test",
        "APP_VERSION": "0.2.0",
        "APP_AUTH_MODE": "local",
        "APP_AUTH_SECRET": secrets.token_urlsafe(48),
        "APP_TICKET_SECRET": secrets.token_urlsafe(48),
        "APP_LOCAL_WEBHOOK_SECRET": secrets.token_urlsafe(48),
        "APP_PAYMENT_PROVIDER": "local",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("APP_STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("APP_STRIPE_WEBHOOK_SECRET", raising=False)
    booking = load_service("booking-service")
    attractions = load_service("attractions-service")
    from datetime import datetime, timedelta, timezone

    def headers(subject="visitor-one", role="visitor", **claims):
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "sub": subject,
                "role": role,
                "kind": "access",
                "iss": "wonderland-local",
                "aud": "wonderland-local",
                "iat": now,
                "exp": now + timedelta(minutes=5),
                **claims,
            },
            booking.settings.auth_secret.get_secret_value(),
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}

    with (
        TestClient(booking.app) as booking_client,
        TestClient(attractions.app) as attraction_client,
    ):
        yield {
            "booking": booking_client,
            "attractions": attraction_client,
            "module": booking,
            "headers": headers,
            "engine": postgres_engine,
        }
    booking.app.state.engine.dispose()
    attractions.app.state.engine.dispose()
