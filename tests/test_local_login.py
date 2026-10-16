import json
import stat

from dotenv import dotenv_values
from fastapi.testclient import TestClient
import pytest

from conftest import load_service
from scripts.local.accounts import ensure_accounts
from wonderland_common.config import Settings
from wonderland_common.local_login import password_hash


@pytest.fixture
def login_client(monkeypatch):
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_AUTH_MODE", "local")
    monkeypatch.setenv("APP_AUTH_SECRET", "ephemeral-local-login-signing-secret-12345")
    accounts = {
        email: {
            "subject": subject,
            "role": role,
            "password_hash": password_hash("ephemeral-test-password"),
        }
        for email, subject, role in [
            ("visitor@example.test", "existing-visitor", "visitor"),
            ("admin@example.test", "existing-admin", "admin"),
        ]
    }
    monkeypatch.setenv("APP_LOCAL_ACCOUNTS_JSON", json.dumps(accounts))
    with TestClient(load_service("booking-service").app) as client:
        yield client


def credentials(portal="visitor", **changes):
    return {
        "email": f"{portal}@example.test",
        "password": "ephemeral-test-password",
        "portal": portal,
        **changes,
    }


@pytest.mark.parametrize(
    "portal,subject", [("visitor", "existing-visitor"), ("admin", "existing-admin")]
)
def test_password_login_uses_server_role_and_existing_subject(
    login_client, portal, subject
):
    response = login_client.post("/auth/local-login", json=credentials(portal))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    identity = login_client.get(
        "/identity",
        headers={"Authorization": "Bearer " + response.json()["access_token"]},
    )
    assert identity.json()["subject"] == subject
    assert identity.json()["role"] == portal
    if portal == "visitor":
        assert (
            login_client.get(
                "/admin/ticket-tiers",
                headers={"Authorization": "Bearer " + response.json()["access_token"]},
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "body",
    [
        credentials(password="incorrect-password"),
        credentials(email="unknown@example.test"),
        credentials(portal="admin", email="visitor@example.test"),
        credentials(portal="visitor", email="admin@example.test"),
    ],
)
def test_invalid_password_or_wrong_portal_does_not_issue_token(login_client, body):
    response = login_client.post("/auth/local-login", json=body)
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Email or password is incorrect for this portal"
    }


def test_role_injection_rejected_and_validation_does_not_echo_password(login_client):
    response = login_client.post("/auth/local-login", json=credentials(role="admin"))
    assert response.status_code == 422
    assert "ephemeral-test-password" not in response.text


def test_password_login_is_bounded(login_client):
    for _ in range(20):
        assert (
            login_client.post(
                "/auth/local-login", json=credentials(password="incorrect-password")
            ).status_code
            == 401
        )
    response = login_client.post("/auth/local-login", json=credentials())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize(
    "environment,auth_mode,status",
    [("local", "disabled", 404), ("aws", "disabled", 404), ("local", "local", 503)],
)
def test_local_login_fails_closed_without_local_configuration(
    monkeypatch, environment, auth_mode, status
):
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENVIRONMENT", environment)
    monkeypatch.setenv("APP_AUTH_MODE", auth_mode)
    monkeypatch.setenv("APP_AUTH_SECRET", "ephemeral-local-login-signing-secret-12345")
    with TestClient(load_service("booking-service").app) as client:
        assert (
            client.post("/auth/local-login", json=credentials()).status_code == status
        )


def test_local_accounts_are_private_hashed_and_preserved(tmp_path):
    env_file = tmp_path / "local.env"
    env_file.write_text("APP_ENVIRONMENT=local\nAPP_AUTH_MODE=local\n")
    path = ensure_accounts(env_file)
    original = path.read_bytes()
    original_env = env_file.read_bytes()
    accounts = json.loads(path.read_text())
    hashed = json.loads(dotenv_values(env_file)["APP_LOCAL_ACCOUNTS_JSON"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    for account in accounts:
        assert account["password"] not in env_file.read_text()
        saved = hashed[account["email"]]["password_hash"]
        assert password_hash(account["password"], saved.split(":")[0]) == saved
    assert ensure_accounts(env_file) == path
    assert path.read_bytes() == original
    assert env_file.read_bytes() == original_env


def test_local_account_configuration_rejected_in_cloud():
    with pytest.raises(ValueError, match="prohibited"):
        Settings(environment="aws", auth_mode="disabled", local_accounts_json="{}")
