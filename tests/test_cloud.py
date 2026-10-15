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


def hosting_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "ROOT", tmp_path)
    persistent = {
        "pool_id": "us-east-1_offline", "client_id": "offlineclient",
        "amplify_app_id": "visitor-app", "admin_amplify_app_id": "admin-app",
        "frontend_origin": "https://visitor.example.com",
        "admin_origin": "https://admin.example.com",
    }
    monkeypatch.setattr(cloud, "outputs", lambda stage: persistent if stage == "persistent"
                        else {"api_url": "https://api.example.com"})
    for directory, title in [("dist", "Visitor"), ("dist-admin", "Admin")]:
        build = tmp_path / "frontend" / directory
        build.mkdir(parents=True)
        (build / "index.html").write_text(title)
        (build / "assets").mkdir()
        (build / "assets/app.js").write_text(title + " script")
    commands, created, uploads = [], [], []
    monkeypatch.setenv("VITE_DEMO_MODE", "true")
    monkeypatch.setattr(cloud, "command", lambda argv, **kw: commands.append((argv, kw)))
    def create(**kw):
        created.append(kw["appId"])
        return {"jobId": "job", "zipUploadUrl": "https://upload.invalid/private"}
    amplify = SimpleNamespace(
        create_deployment=create,
        start_deployment=lambda **kw: None,
        get_job=lambda **kw: {"job": {"summary": {"status": "SUCCEED"}}},
    )
    def upload(url, content, **kw):
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            uploads.append({name: archive.read(name) for name in archive.namelist()})
        return SimpleNamespace(status_code=200)
    monkeypatch.setattr(cloud.httpx, "put", upload)
    return persistent, commands, created, uploads, amplify


def test_hosting_publishes_both_distinct_builds_with_demo_disabled(tmp_path, monkeypatch):
    _, commands, created, uploads, amplify = hosting_fixture(tmp_path, monkeypatch)
    cloud.hosting(SimpleNamespace(client=lambda name: amplify), target())
    assert created == ["visitor-app", "admin-app"]
    assert [upload["index.html"] for upload in uploads] == [b"Visitor", b"Admin"]
    assert all("assets/app.js" in upload for upload in uploads)
    assert commands[0][1]["env"]["VITE_DEMO_MODE"] == "false"
    assert commands[0][1]["env"]["VITE_AUTH_MODE"] == "cognito"


def test_hosting_missing_admin_build_refuses_before_upload(tmp_path, monkeypatch):
    _, _, created, _, amplify = hosting_fixture(tmp_path, monkeypatch)
    (tmp_path / "frontend/dist-admin/index.html").unlink()
    with pytest.raises(cloud.GuardError, match="Both visitor and admin"):
        cloud.hosting(SimpleNamespace(client=lambda name: amplify), target())
    assert created == []


def test_admin_hosting_failure_is_reported(tmp_path, monkeypatch):
    _, _, _, _, amplify = hosting_fixture(tmp_path, monkeypatch)
    amplify.get_job = lambda **kw: {"job": {"summary": {
        "status": "FAILED" if kw["appId"] == "admin-app" else "SUCCEED"
    }}}
    with pytest.raises(ValueError, match="admin deployment failed"):
        cloud.hosting(SimpleNamespace(client=lambda name: amplify), target())


@pytest.mark.parametrize("bad_origin", [None, "admin", "unapproved"])
def test_cloud_verify_checks_both_origins_and_rejects_unapproved(monkeypatch, bad_origin):
    portals = {"frontend_origin": "https://visitor.example.com",
               "admin_origin": "https://admin.example.com"}
    monkeypatch.setattr(cloud, "connect_cluster", lambda *a: None)
    monkeypatch.setattr(cloud, "outputs", lambda stage:
                        portals if stage == "persistent" else
                        {"api_url": "https://api.example.com", "dead_queue_url": "offline"})
    monkeypatch.setattr(cloud.httpx, "get", lambda url, **kw:
                        SimpleNamespace(status_code=401 if url.endswith(
                            ("/bookings", "/visits", "/admin/analytics")) else 200))
    requested = []
    def options(url, headers, **kw):
        origin = headers["Origin"]
        requested.append(origin)
        allowed = origin in portals.values()
        if bad_origin == "admin" and origin == portals["admin_origin"]:
            allowed = False
        if bad_origin == "unapproved":
            allowed = True
        return SimpleNamespace(status_code=204,
                               headers={"access-control-allow-origin": origin} if allowed else {})
    monkeypatch.setattr(cloud.httpx, "options", options)
    session = SimpleNamespace(client=lambda name: SimpleNamespace(
        get_queue_attributes=lambda **kw: {"Attributes": {"ApproximateNumberOfMessages": "0"}}))
    if bad_origin:
        with pytest.raises(cloud.GuardError, match="CORS failed|unapproved browser"):
            cloud.verify(session, target())
    else:
        cloud.verify(session, target())
        assert requested == [*portals.values(), "https://unapproved.invalid"]


def test_edge_variables_include_both_hosted_origins(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "ROOT", tmp_path)
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets/edge-discovery.json").write_text(json.dumps({
        "listener_arn": "offline-listener", "alb_security_group_id": "offline-sg"
    }))
    monkeypatch.setattr(cloud, "outputs", lambda stage: {
        "demo": {"vpc_id": "offline-vpc", "private_subnets": ["a", "b"]},
        "persistent": {"frontend_origin": "https://visitor.example.com",
                       "admin_origin": "https://admin.example.com"},
    }[stage])
    values = cloud.tfvars({**target(), "tls_server_name": "api.example.com"}, "edge")
    assert values["frontend_origin"] == "https://visitor.example.com"
    assert values["admin_origin"] == "https://admin.example.com"


def test_root_env_credentials_replace_stale_shell_token(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "ROOT", tmp_path)
    for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
                'AWS_PROFILE', 'AWS_DEFAULT_PROFILE', 'AWS_REGION', 'AWS_DEFAULT_REGION']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'stale-offline-token')
    monkeypatch.setenv('AWS_PROFILE', 'unused-profile')
    (tmp_path / '.env').write_text('AWS_ACCESS_KEY_ID=offline-id\nAWS_SECRET_ACCESS_KEY=offline-secret\nAWS_REGION=us-east-1\nAPP_AUTH_MODE=disabled\n')
    credentials = cloud.aws_environment(target())
    assert credentials['aws_access_key_id'] == 'offline-id'
    assert credentials['aws_session_token'] is None
    assert 'AWS_SESSION_TOKEN' not in cloud.os.environ
    assert 'AWS_PROFILE' not in cloud.os.environ
    assert cloud.cloud_profile(target()) == {}
    assert 'profile' not in cloud.backend({**target(), 'state_bucket': 'offline'}, 'demo')


@pytest.mark.parametrize('content', [
    'AWS_ACCESS_KEY_ID=offline-id\n',
    'AWS_ACCESS_KEY_ID=offline-id\nAWS_SECRET_ACCESS_KEY=offline-secret\nAWS_REGION=eu-west-1\n',
])
def test_invalid_env_credentials_fail_before_session_creation(tmp_path, monkeypatch, content):
    monkeypatch.setattr(cloud, 'ROOT', tmp_path)
    (tmp_path / '.env').write_text(content)
    calls = []
    monkeypatch.setattr(cloud.boto3, 'Session', lambda **kw: calls.append(kw))
    with pytest.raises(cloud.GuardError):
        cloud.account_session(SimpleNamespace(allow_account_access=True), target())
    assert calls == []


def test_stripe_root_env_selection_and_review_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, 'ROOT', tmp_path)
    monkeypatch.setattr(cloud, 'source_digest', lambda: 'offline-source')
    p = tmp_path / '.env'
    p.write_text('APP_STRIPE_SECRET_KEY=sk_test_offline\nAPP_STRIPE_WEBHOOK_SECRET=whsec_offline\n')
    assert cloud.stripe_values()['APP_STRIPE_SECRET_KEY'] == 'sk_test_offline'
    before = cloud.review_spec(target(), 'update-payment')['private_input_sha256']
    p.write_text('APP_STRIPE_SECRET_KEY=sk_test_offline\nAPP_STRIPE_WEBHOOK_SECRET=whsec_changed\n')
    assert before != cloud.review_spec(target(), 'update-payment')['private_input_sha256']
    p.write_text('APP_STRIPE_SECRET_KEY=sk_live_offline\nAPP_STRIPE_WEBHOOK_SECRET=whsec_offline\n')
    with pytest.raises(cloud.GuardError, match='Stripe test'):
        cloud.stripe_values()


def test_stripe_legacy_file_fallback_does_not_mix_partial_root_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, 'ROOT', tmp_path)
    (tmp_path / 'secrets').mkdir()
    (tmp_path / 'secrets/stripe.env').write_text('APP_STRIPE_SECRET_KEY=sk_test_legacy\nAPP_STRIPE_WEBHOOK_SECRET=whsec_legacy\n')
    (tmp_path / '.env').write_text('APP_STRIPE_SECRET_KEY=\nAPP_STRIPE_WEBHOOK_SECRET=\n')
    assert cloud.stripe_values()['APP_STRIPE_SECRET_KEY'] == 'sk_test_legacy'
    (tmp_path / '.env').write_text('APP_STRIPE_SECRET_KEY=sk_test_partial\n')
    with pytest.raises(cloud.GuardError):
        cloud.stripe_values()
