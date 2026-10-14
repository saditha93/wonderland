import importlib.util
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICES = [
    "attractions-service",
    "booking-service",
    "gate-ride-service",
    "analytics-worker",
]


@pytest.fixture(params=SERVICES)
def service(request, monkeypatch):
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_AUTH_MODE", "disabled")
    monkeypatch.setenv("APP_ENVIRONMENT", "local")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    from conftest import load_service

    module = load_service(request.param)
    return request.param, module


@pytest.mark.parametrize(
    "endpoint,scope",
    [
        ("/health", "skeleton-only"),
        ("/health/live", "process"),
        ("/health/ready", "skeleton-only"),
    ],
)
def test_health_contract(service, endpoint, scope):
    name, module = service
    with TestClient(module.app) as client:
        response = client.get(endpoint)
    domain_service = name in {
        "attractions-service",
        "booking-service",
        "gate-ride-service",
    }
    expected_status = 503 if domain_service and endpoint == "/health/ready" else 200
    expected_scope = (
        ("database" if endpoint == "/health/ready" else "process")
        if domain_service
        else scope
    )
    assert response.status_code == expected_status
    assert response.json() == {
        "service": name,
        "status": "ok" if expected_status == 200 else "unavailable",
        "version": "0.1.0",
        "environment": "local",
        "scope": expected_scope,
    }
    assert response.headers["x-request-id"]


def test_request_correlation_and_private_data_not_logged(service):
    _, module = service
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(json.loads(record.getMessage()))

    handler = Capture()
    module.logger.addHandler(handler)
    try:
        with TestClient(module.app) as client:
            response = client.get(
                "/health?token=PRIVATE_QUERY",
                headers={
                    "X-Request-ID": "demo-request-1",
                    "Authorization": "Bearer PRIVATE_TOKEN",
                },
            )
        assert response.headers["x-request-id"] == "demo-request-1"
        assert records[-1]["request_id"] == "demo-request-1"
        assert records[-1]["route"] == "/health"
        assert records[-1]["duration_ms"] >= 0
        assert "PRIVATE" not in json.dumps(records)
    finally:
        module.logger.removeHandler(handler)


def test_invalid_request_id_is_replaced(service):
    _, module = service
    with TestClient(module.app) as client:
        response = client.get("/health", headers={"X-Request-ID": "unsafe value"})
    assert response.headers["x-request-id"] != "unsafe value"
    assert module.SAFE_REQUEST_ID.fullmatch(response.headers["x-request-id"])


def test_domain_endpoints_are_not_faked(service):
    _, module = service
    with TestClient(module.app) as client:
        assert client.get("/bookings").status_code == (
            503 if service[0] == "booking-service" else 404
        )
