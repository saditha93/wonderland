"""Offline security and plan approval checks for the small AWS demo."""

import json
from types import SimpleNamespace
import pytest
from scripts.aws import cli as cloud
from scripts.aws.workloads import render
from scripts.aws.workload_templates import tls_material, SERVICES


def test_root_or_wrong_identity_cannot_deploy(monkeypatch):
    monkeypatch.setattr(cloud, "aws_environment", lambda t: {})
    fake = SimpleNamespace(
        client=lambda name: SimpleNamespace(
            get_caller_identity=lambda: {
                "Account": "111111111111",
                "Arn": "arn:aws:iam::111111111111:root",
            }
        )
    )
    monkeypatch.setattr(cloud.boto3, "Session", lambda **kwargs: fake)
    with pytest.raises(ValueError, match="non-root"):
        cloud.create_aws_session({"account_id": "111111111111", "region": "us-east-1"})


def test_paid_plan_never_implicitly_accepted():
    fake = SimpleNamespace(
        client=lambda name: SimpleNamespace(
            get_account_plan_state=lambda: {
                "accountPlanType": "PAID",
                "accountPlanStatus": "ACTIVE",
            }
        )
    )
    with pytest.raises(ValueError, match="no automatic upgrade"):
        cloud.require_free_plan(fake)


def test_changed_saved_plan_refused_before_aws_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "PRIVATE", tmp_path)
    (tmp_path / "deployment.tfplan").write_bytes(b"changed")
    (tmp_path / "review.json").write_text(json.dumps({"plan_sha256": "approved"}))
    with pytest.raises(ValueError, match="exact saved plan"):
        cloud.deploy(None, {}, "approved")


def test_single_node_tls_and_private_administration():
    t = {"region": "us-east-1", "release": "r-test"}
    d = {
        "queue_url": "https://sqs.us-east-1.amazonaws.com/111111111111/events",
        "dead_queue_url": "https://sqs.us-east-1.amazonaws.com/111111111111/dead",
        "pool_id": "us-east-1_Test",
        "client_id": "test",
        "portals": {"visitor": {"origin": "https://demo.test.amplifyapp.com"}},
        "repositories": {
            name: "example/" + name for name in [*SERVICES, "frontend", "migrate"]
        },
    }
    values = {
        key: "postgresql+psycopg://user:private@postgres/wonderland"
        for key in SERVICES.values()
    }
    values.update(
        APP_TICKET_PRIVATE_KEY_B64="private",
        APP_TICKET_PUBLIC_KEY_B64="public",
        APP_TICKET_OWNER_SECRET="owner",
        APP_STRIPE_SECRET_KEY="sk_test_private",
        APP_STRIPE_WEBHOOK_SECRET="whsec_private",
        LOCAL_METABASE_ROLE_PASSWORD="meta",
    )
    tls = tls_material(["postgres"])
    docs = render(
        t,
        d,
        {
            "values": values,
            "master": {"username": "wonderland_owner", "password": "private"},
            "tls": tls,
        },
    )
    assert not any(x["kind"] == "Ingress" for x in docs)
    services = [x for x in docs if x["kind"] == "Service"]
    assert [
        (x["metadata"]["name"], x["spec"].get("type"))
        for x in services
        if x["spec"].get("type") == "NodePort"
    ] == [("frontend", "NodePort")]
    ca = next(x for x in docs if x["metadata"]["name"] == "rds-ca")
    assert ca["data"]["global-bundle.pem"] == tls["ca"]
    pg = next(x for x in docs if x["kind"] == "StatefulSet")["spec"]["template"][
        "spec"
    ]["containers"][0]
    assert "ssl=on" in pg["args"]
    hba = next(x for x in docs if x["metadata"]["name"] == "postgres-hba")["data"][
        "pg_hba.conf"
    ]
    assert "hostssl" in hba and "host all" not in hba
    for x in docs:
        if x["kind"] == "Secret":
            for v in x["stringData"].values():
                if v.startswith("postgresql"):
                    assert "sslmode=verify-full" in v
                    assert (
                        "%2Frun%2Frds-ca%2Fglobal-bundle.pem" in v
                        or "/run/rds-ca/global-bundle.pem" in v
                    )
        if x["kind"] in {"Deployment", "Job"}:
            pod = x["spec"]["template"]["spec"]
            assert pod["imagePullSecrets"] == [{"name": "ecr-pull"}]
            assert pod["automountServiceAccountToken"] is False
            assert not any(
                e["name"] == "APP_AUTH_SECRET"
                for c in pod["containers"]
                for e in c.get("env", [])
            )


def test_destroy_requires_explicit_scope_before_backup_or_mutation(monkeypatch):
    from scripts.aws import cleanup

    monkeypatch.setattr(
        cleanup, "backup", lambda *args: pytest.fail("Backup unexpectedly started")
    )
    monkeypatch.setattr(
        cleanup,
        "run_terraform",
        lambda *args, **kwargs: pytest.fail("Unexpected Terraform mutation"),
    )
    with pytest.raises(ValueError, match="destroy-wonderland-demo"):
        cleanup.destroy(None, {}, None, None)


def test_deployment_plan_refuses_a_leftover_destroy_override(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "TFROOT", tmp_path)
    (tmp_path / "cleanup_override.tf.json").write_text("{}")
    with pytest.raises(ValueError, match="interrupted cleanup"):
        cloud.plan(None, {})
