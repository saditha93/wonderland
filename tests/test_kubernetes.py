"""Validate deployment safety contracts before any local cluster mutation."""

from pathlib import Path
import importlib.util
import subprocess
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]


def documents():
    return [
        d
        for path in (ROOT / "infrastructure/kubernetes").glob("**/*.yaml")
        if path.name != "kustomization.yaml" and "aws" not in path.parts
        for d in yaml.safe_load_all(path.read_text())
        if d
    ]


def test_service_selectors_match_workloads():
    docs = documents()
    pods = [
        d["spec"]["template"]["metadata"]["labels"]
        for d in docs
        if d["kind"] in {"Deployment", "StatefulSet"}
    ]
    for service in [d for d in docs if d["kind"] == "Service"]:
        selector = service["spec"]["selector"]
        assert any(
            all(labels.get(k) == v for k, v in selector.items()) for labels in pods
        )


def test_workloads_have_bounded_resources_and_no_api_tokens():
    for doc in documents():
        if doc["kind"] not in {"Deployment", "StatefulSet", "Job"}:
            continue
        spec = doc["spec"]["template"]["spec"]
        assert spec["automountServiceAccountToken"] is False
        assert spec["securityContext"]["runAsNonRoot"] is True
        for container in spec["containers"]:
            assert container["resources"]["requests"]["cpu"]
            assert container["resources"]["limits"]["memory"]
            assert container["securityContext"]["allowPrivilegeEscalation"] is False
            assert container["securityContext"]["readOnlyRootFilesystem"] is True
            assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_probes_distinguish_dependency_failure_from_process_death():
    for doc in documents():
        if doc["kind"] != "Deployment" or doc["metadata"]["name"] == "frontend":
            continue
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
        assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
        assert container["startupProbe"]["httpGet"]["path"] == "/health/live"


def test_private_ticket_key_is_exclusive_to_booking():
    for doc in documents():
        if doc["kind"] != "Deployment":
            continue
        container = doc["spec"]["template"]["spec"]["containers"][0]
        secrets = {
            e["valueFrom"]["secretKeyRef"]["name"]
            for e in container.get("env", [])
            if "valueFrom" in e
        }
        assert ("booking-ticket" in secrets) == (
            doc["metadata"]["name"] == "booking-service"
        )
        assert "migration-config" not in secrets
        assert all("secretRef" not in item for item in container.get("envFrom", []))


def test_hpa_targets_blue_with_cpu_request_and_bounded_replicas():
    docs = documents()
    hpa = next(d for d in docs if d["kind"] == "HorizontalPodAutoscaler")["spec"]
    target = next(
        d for d in docs if d["metadata"]["name"] == hpa["scaleTargetRef"]["name"]
    )
    assert target["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"][
        "cpu"
    ]
    assert 2 <= hpa["minReplicas"] < hpa["maxReplicas"] <= 3
    assert hpa["metrics"][0]["resource"]["target"]["averageUtilization"] > 0


def test_secrets_are_generated_in_memory_and_scoped():
    spec = importlib.util.spec_from_file_location(
        "local_kubernetes", ROOT / "scripts/local-kubernetes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    keys = [
        "POSTGRES_PASSWORD",
        "APP_AUTH_SECRET",
        "ATTRACTIONS_DATABASE_URL",
        "BOOKING_DATABASE_URL",
        "GATE_DATABASE_URL",
        "ANALYTICS_DATABASE_URL",
        "APP_TICKET_PRIVATE_KEY_B64",
        "APP_TICKET_PUBLIC_KEY_B64",
        "APP_TICKET_OWNER_SECRET",
        "APP_LOCAL_WEBHOOK_SECRET",
        "MIGRATION_DATABASE_URL",
        "LOCAL_REPORTING_ROLE_PASSWORD",
    ]
    docs = list(
        yaml.safe_load_all(
            module.secrets_manifest({key: "private-test-placeholder" for key in keys})
        )
    )
    assert all(d["metadata"]["namespace"] == "wonderland" for d in docs)
    migration = next(d for d in docs if d["metadata"]["name"] == "migration-config")
    assert "APP_TICKET_PRIVATE_KEY_B64" not in migration["stringData"]
    assert not any(d["kind"] == "Secret" for d in documents())


def test_blue_green_have_disjoint_selectors_and_compatible_images():
    docs = documents()
    blue = next(d for d in docs if d["metadata"]["name"] == "attractions-service-blue")
    green = next(
        d for d in docs if d["metadata"]["name"] == "attractions-service-green"
    )
    assert blue["spec"]["selector"] != green["spec"]["selector"]
    assert blue["spec"]["selector"]["matchLabels"]["color"] == "blue"
    assert green["spec"]["selector"]["matchLabels"]["color"] == "green"
    assert any(
        e.get("value") == "0.5.1"
        for e in green["spec"]["template"]["spec"]["containers"][0]["env"]
    )


def test_database_preflight_failure_does_not_leak_credentials():
    import os, sys

    marker = "NEVER_LOG_THIS_TEST_PASSWORD"
    env = {
        **os.environ,
        "TEST_DATABASE_URL": f"postgresql+psycopg://offline:{marker}@127.0.0.1:1/offline_test",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_domain.py::test_catalog_search_and_detail",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "Connection details suppressed" in result.stdout
    assert marker not in result.stdout + result.stderr


def test_cluster_guard_rejects_cloud_endpoint(tmp_path, monkeypatch):
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "local_kubernetes_guard", ROOT / "scripts/local-kubernetes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path / "kubeconfig"
    config.write_text(
        yaml.safe_dump(
            {
                "contexts": [
                    {"name": "wonderland", "context": {"cluster": "wonderland"}}
                ],
                "clusters": [
                    {
                        "name": "wonderland",
                        "cluster": {"server": "https://example.eks.amazonaws.com"},
                    }
                ],
            }
        )
    )
    profile = tmp_path / ".minikube/profiles/wonderland/config.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"Driver":"docker"}')
    monkeypatch.setattr(module, "CONFIG", config)
    monkeypatch.setattr(
        module, "run", lambda *a, **kw: SimpleNamespace(stdout="192.168.49.2")
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(SystemExit, match="non-local"):
        module.guard()


def test_stop_is_idempotent_without_live_kubeconfig(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sys

    spec = importlib.util.spec_from_file_location(
        "local_stop", ROOT / "scripts/local-kubernetes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = tmp_path / ".minikube/profiles/wonderland/config.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"Name":"wonderland","Driver":"docker"}')
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(sys, "argv", ["local-kubernetes.py", "stop"])
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            stdout='{"name":"wonderland","status":"Stopped","runtime":"docker"}\n'
        )

    monkeypatch.setattr(module, "run", run)
    module.main()
    assert calls == [["colima", "list", "--json"]]
