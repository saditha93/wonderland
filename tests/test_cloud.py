"""Offline lifecycle safety, rendered cloud configuration and real local TLS checks."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import UUID
import httpx
import pytest
from sqlalchemy import text
from scripts import aws_workloads as workloads
from scripts import cloud
from conftest import load_service


def target():
    return {
        "account_id": "111111111111",
        "region": "us-east-1",
        "name": "wonderland-demo",
        "release": "r20261014-test",
        "profile": "offline",
        "operator_role_arn": "arn:aws:iam::111111111111:role/operator",
        "certificate_arn": "arn:aws:acm:us-east-1:111111111111:certificate/offline",
    }


def test_account_denial_occurs_before_creating_any_sdk_session(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud.boto3, "Session", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ValueError, match="not authorized"):
        cloud.account_session(SimpleNamespace(allow_account_access=False), target())
    assert calls == []


@pytest.mark.parametrize(
    "identity",
    [
        {"Account": "222222222222", "Arn": "arn:aws:iam::222222222222:role/operator"},
        {"Account": "111111111111", "Arn": "arn:aws:iam::111111111111:root"},
        {
            "Account": "111111111111",
            "Arn": "arn:aws:sts::111111111111:assumed-role/wrong/session",
        },
    ],
)
def test_wrong_account_root_and_unapproved_role_are_rejected(monkeypatch, identity):
    session = SimpleNamespace(
        client=lambda *a, **kw: SimpleNamespace(get_caller_identity=lambda: identity)
    )
    monkeypatch.setattr(cloud.boto3, "Session", lambda **kw: session)
    with pytest.raises(ValueError):
        cloud.account_session(SimpleNamespace(allow_account_access=True), target())


def test_mutation_requires_matching_action_hash_and_cost_ack(monkeypatch):
    monkeypatch.setattr(cloud, "source_digest", lambda: "source")
    args = SimpleNamespace(
        action="deploy", approve_action=None, acknowledge_costs=False
    )
    with pytest.raises(ValueError):
        cloud.approve_action(args, target())
    args.approve_action = cloud.digest(cloud.review_spec(target(), "deploy"))
    args.acknowledge_costs = True
    cloud.approve_action(args, target())
    altered = {**target(), "account_id": "222222222222"}
    with pytest.raises(ValueError):
        cloud.approve_action(args, altered)


def test_saved_plan_tampering_and_source_drift_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "ROOT", tmp_path)
    monkeypatch.setattr(cloud, "source_digest", lambda: "source")
    monkeypatch.setattr(cloud, "terraform_digest", lambda: "terraform")
    p = tmp_path / "secrets/demo.tfplan"
    p.parent.mkdir()
    p.write_bytes(b"offline-plan")
    meta = {
        "stage": "demo",
        "target_digest": cloud.digest(target()),
        "plan_sha256": cloud.file_sha(p),
        "source_sha256": "source",
        "terraform_sha256": "terraform",
        "destroy": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    p.with_suffix(".review.json").write_text(json.dumps(meta))
    args = SimpleNamespace(
        stage="demo",
        action="apply",
        approve_plan=meta["plan_sha256"],
        acknowledge_costs=True,
    )
    assert cloud.checked_plan(args, target()) == p
    p.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        cloud.checked_plan(args, target())
    p.write_bytes(b"offline-plan")
    monkeypatch.setattr(cloud, "source_digest", lambda: "changed")
    with pytest.raises(ValueError):
        cloud.checked_plan(args, target())


@pytest.fixture(scope="module")
def material():
    return workloads.tls_material()


def test_cloud_render_uses_cognito_tls_rds_irsa_and_stripe_test_config(material):
    core = {
        "db_endpoint": "database.example.rds.amazonaws.com",
        "alb_security_group_id": "sg-00000000000000000",
        "queue_url": "https://sqs.us-east-1.amazonaws.com/111111111111/demo",
        "dead_queue_url": "https://sqs.us-east-1.amazonaws.com/111111111111/dead",
        "analytics_role_arn": "arn:aws:iam::111111111111:role/analytics",
    }
    persistent = {
        "pool_id": "us-east-1_offline",
        "client_id": "offlineclient",
        "frontend_origin": "https://demo.example.com",
        "repositories": {
            k: "111111111111.dkr.ecr.us-east-1.amazonaws.com/" + k
            for k in [*workloads.SERVICES, "migrate", "frontend"]
        },
    }
    values = {
        key: "postgresql+psycopg://role:offline@postgres/wonderland"
        for key in workloads.SERVICES.values()
    }
    values.update(
        {
            key: "offline-placeholder"
            for key in [
                "APP_TICKET_PRIVATE_KEY_B64",
                "APP_TICKET_PUBLIC_KEY_B64",
                "APP_TICKET_OWNER_SECRET",
                "APP_STRIPE_SECRET_KEY",
                "APP_STRIPE_WEBHOOK_SECRET",
                "LOCAL_METABASE_ROLE_PASSWORD",
            ]
        }
    )
    docs = workloads.render(
        target(),
        core,
        persistent,
        values,
        {"username": "wonderland_owner", "password": "offline-password"},
        material,
    )
    cm = next(
        d
        for d in docs
        if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "app-config"
    )["data"]
    assert cm["APP_AUTH_MODE"] == "cognito" and cm["APP_ENVIRONMENT"] == "aws"
    assert cm["APP_ATTRACTIONS_URL"].startswith("https://")
    for doc in docs:
        if doc["kind"] != "Deployment" or doc["metadata"]["name"] == "metabase":
            continue
        c = doc["spec"]["template"]["spec"]["containers"][0]
        assert c["readinessProbe"]["httpGet"]["scheme"] == "HTTPS"
        assert not any(
            e["name"] in {"APP_AUTH_SECRET", "APP_LOCAL_WEBHOOK_SECRET", "APP_LOCAL_ACCOUNTS_JSON"}
            for e in c.get("env", [])
        )
        if doc["metadata"]["name"] == "analytics-worker":
            assert (
                doc["spec"]["template"]["spec"]["serviceAccountName"]
                == "analytics-worker"
            )
            assert any(
                e.get("name") == "APP_ANALYTICS_TRANSPORT" and e.get("value") == "sqs"
                for e in c["env"]
            )
    metadata = next(
        d
        for d in docs
        if d["kind"] == "Secret" and d["metadata"]["name"] == "metabase-db"
    )["stringData"]
    assert "password=" not in metadata["uri"]
    assert "sslmode=verify-full" in metadata["uri"]
    urls = [
        d["stringData"]["database-url"]
        for d in docs
        if d["kind"] == "Secret" and "database-url" in d.get("stringData", {})
    ]
    assert all("sslmode=verify-full" in u and "sslrootcert=" in u for u in urls)
    for d in docs:
        if d["kind"] == "Deployment":
            assert d["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"]
            assert (
                "wonderland/secret-config-hash"
                in d["spec"]["template"]["metadata"]["annotations"]
            )
    assert not any(d["kind"] == "StatefulSet" for d in docs)
    assert any(
        d["kind"] == "Service" and d["metadata"]["name"] == "metabase" for d in docs
    )
    nginx = next(
        d
        for d in docs
        if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "nginx-cloud"
    )["data"]["default.conf"]
    assert "proxy_ssl_verify on" in nginx and "proxy_pass http://" not in nginx
    assert "listen 8081" not in nginx
    assert "/usr/share/nginx/admin" not in nginx
    ingress = next(d for d in docs if d["kind"] == "Ingress")
    assert (
        ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/backend-protocol"]
        == "HTTPS"
    )


def test_internal_ca_is_actually_verified_by_catalog_client(
    tmp_path, material, monkeypatch
):
    for name, content in [
        ("ca.pem", material["ca"]),
        ("server.pem", material["services"]["attractions-service"]["tls.crt"]),
        ("server.key", material["services"]["attractions-service"]["tls.key"]),
    ]:
        p = tmp_path / name
        p.write_text(content)
        p.chmod(0o600)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(
                {
                    "id": str(UUID(int=101)),
                    "name": "TLS Coaster",
                    "operational_status": "open",
                }
            ).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path / "server.pem", tmp_path / "server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "https://localhost:" + str(server.server_port)
    try:
        with pytest.raises(httpx.ConnectError):
            httpx.get(url, timeout=3)
        from wonderland_common.config import Settings
        import os

        monkeypatch.setenv("APP_INTERNAL_CA_PATH", str(tmp_path / "ca.pem"))
        monkeypatch.setenv("APP_ATTRACTIONS_URL", url)
        module = load_service("gate-ride-service")
        assert module.app.state.catalog.get(UUID(int=101))["name"] == "TLS Coaster"
        if module.app.state.engine:
            module.app.state.engine.dispose()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_sqs_poison_does_not_starve_valid_messages(domain):
    module = load_service("analytics-worker")
    from importlib import import_module

    adapter = import_module(module.__package__ + ".sqs_transport")
    from test_phase4 import envelope

    deleted = []

    class Client:
        def receive_message(self, **kw):
            return {
                "Messages": [
                    {"Body": "not-json", "ReceiptHandle": "poison"},
                    {"Body": json.dumps(envelope()), "ReceiptHandle": "valid"},
                ]
            }

        def delete_message(self, **kw):
            deleted.append(kw["ReceiptHandle"])

    assert (
        adapter.SqsTransport(Client(), "https://sqs.invalid/offline").consume(
            domain["engine"]
        )
        == 1
    )
    assert deleted == ["valid"]
    with domain["engine"].connect() as c:
        assert c.execute(text("SELECT count(*) FROM reporting.arrivals")).scalar() == 1
    module.app.state.engine.dispose()


def test_cloud_settings_fail_closed_for_local_auth_and_wrong_queue_region():
    from wonderland_common.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(environment="aws", auth_mode="local", auth_secret="a" * 48)
    with pytest.raises(ValidationError):
        Settings(
            analytics_transport="sqs",
            aws_region="us-east-1",
            sqs_queue_url="http://localhost/queue",
        )


@pytest.mark.parametrize("stage", ["bootstrap", "persistent"])
def test_persistent_or_state_destroy_is_refused_before_cloud_access(
    tmp_path, monkeypatch, stage
):
    monkeypatch.setattr(cloud, "ROOT", tmp_path)
    monkeypatch.setattr(cloud, "source_digest", lambda: "source")
    monkeypatch.setattr(cloud, "terraform_digest", lambda: "terraform")
    p = tmp_path / "secrets" / (stage + ".tfplan")
    p.parent.mkdir()
    p.write_bytes(b"offline-destroy-plan")
    meta = {
        "stage": stage,
        "target_digest": cloud.digest(target()),
        "plan_sha256": cloud.file_sha(p),
        "source_sha256": "source",
        "terraform_sha256": "terraform",
        "destroy": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    p.with_suffix(".review.json").write_text(json.dumps(meta))
    args = SimpleNamespace(
        stage=stage,
        action="destroy",
        approve_plan=meta["plan_sha256"],
        acknowledge_costs=True,
    )
    with pytest.raises(ValueError, match="temporary"):
        cloud.checked_plan(args, target())


def test_log_collection_cannot_match_vendor_migration_or_other_namespace_logs():
    import fnmatch

    docs = workloads.log_collector(
        {"region": "us-east-1"},
        {
            "logs_role_arn": "arn:aws:iam::111111111111:role/logs",
            "application_log_group": "/wonderland/offline/application",
        },
    )
    config = next(d for d in docs if d["kind"] == "ConfigMap")["data"][
        "fluent-bit.conf"
    ]
    pattern = next(
        line.strip().split(" ", 1)[1]
        for line in config.splitlines()
        if line.strip().startswith("Path ")
    )
    assert fnmatch.fnmatch(
        "/var/log/containers/booking-service-abc_wonderland_api-123.log", pattern
    )
    for filename in [
        "metabase-abc_wonderland_metabase-123.log",
        "schema-migrate-abc_wonderland_migrate-123.log",
        "api-abc_other_api-123.log",
    ]:
        assert not fnmatch.fnmatch("/var/log/containers/" + filename, pattern)
    pod = next(d for d in docs if d["kind"] == "DaemonSet")["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert next(v for v in pod["containers"][0]["volumeMounts"] if v["name"] == "logs")[
        "readOnly"
    ]
    assert pod["containers"][0]["securityContext"]["capabilities"]["drop"] == ["ALL"]
