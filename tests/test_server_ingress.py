"""Routing and server-control checks without creating AWS resources."""

import importlib.util
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def node(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "server_node", ROOT / "infrastructure/aws/node.py"
    )
    module = importlib.util.module_from_spec(spec)
    previous_umask = os.umask(0o077)
    try:
        spec.loader.exec_module(module)
    finally:
        os.umask(previous_umask)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def test_routes_strip_only_their_prefix_and_verify_service_certificates():
    routes = list(
        yaml.safe_load_all(
            (ROOT / "infrastructure/kubernetes/aws/ingress.yaml").read_text()
        )
    )
    expected = {
        "attractions": "attractions-service",
        "booking": "booking-service",
        "gate": "gate-ride-service",
        "analytics": "analytics-worker",
    }
    assert len(routes) == len(expected)
    for route in routes:
        path = route["spec"]["rules"][0]["http"]["paths"][0]
        api = route["metadata"]["name"].removeprefix("api-")
        service = expected[api]
        annotations = route["metadata"]["annotations"]
        prefix = "nginx.ingress.kubernetes.io/"
        assert annotations[prefix + "backend-protocol"] == "HTTPS"
        assert annotations[prefix + "proxy-ssl-verify"] == "on"
        assert annotations[prefix + "proxy-ssl-server-name"] == "on"
        assert annotations[prefix + "proxy-ssl-name"] == service
        assert annotations[prefix + "proxy-ssl-secret"] == "wonderland/ingress-ca"
        assert annotations[prefix + "enable-access-log"] == "false"
        assert route["spec"]["tls"] == [{"secretName": "frontend-tls"}]
        assert path["backend"]["service"] == {"name": service, "port": {"number": 8000}}
        assert path["pathType"] == "ImplementationSpecific"
        assert annotations[prefix + "rewrite-target"] == "/$2"
        pattern = path["path"]
        for suffix in ["", "/", "/health", "/bookings/123"]:
            match = re.fullmatch(pattern, "/api/" + api + suffix)
            assert match is not None
            assert "/" + match[2] == (suffix or "/")
        assert re.match(pattern, "/api/" + api + "-other/health") is None
        assert re.match(pattern, "/metabase/api/health") is None


def test_controller_reuses_builtin_addon_with_private_default_certificate(
    node, monkeypatch
):
    calls = []
    original = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "controller",
                            "args": [
                                "/nginx-ingress-controller",
                                "--default-ssl-certificate=old/old",
                            ],
                        }
                    ]
                }
            }
        }
    }

    def command(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps(original) if "get" in args else "")

    monkeypatch.setattr(node, "command", command)
    applied = []
    monkeypatch.setattr(node, "apply", applied.extend)
    route = {"kind": "Ingress", "metadata": {"name": "api-booking"}}
    node.configure_ingress([route, {"kind": "Secret"}])
    patches = [json.loads(c[-1]) for c in calls if "patch" in c]
    assert patches[0]["data"] == {
        "disable-access-log": "true",
        "allow-snippet-annotations": "false",
    }
    args = patches[1]["spec"]["template"]["spec"]["containers"][0]["args"]
    assert args == [
        "/nginx-ingress-controller",
        "--default-ssl-certificate=wonderland/frontend-tls",
    ]
    assert applied == [route]
    assert any("rollout" in c and "--timeout=300s" in c for c in calls)


@pytest.mark.parametrize("address", ["8.8.8.8", "not-an-ip", "::1"])
def test_host_proxy_rejects_unexpected_cluster_address(node, monkeypatch, address):
    monkeypatch.setattr(
        node, "command", lambda *a, **kw: SimpleNamespace(stdout=address)
    )
    with pytest.raises(ValueError):
        node.configure_proxy({}, {"tls": {"ca": "test-ca"}, "origin_token": "test"})


def test_host_proxy_uses_private_node_and_keeps_gateway_guard_before_preflight(
    node, monkeypatch, tmp_path
):
    host = tmp_path / "host"
    for folder in [
        "etc/nginx/sites-available",
        "etc/systemd/system",
        "etc/letsencrypt/live/wonderland-ip",
    ]:
        (host / folder).mkdir(parents=True, exist_ok=True)
    (host / "etc/letsencrypt/live/wonderland-ip/fullchain.pem").touch()
    original_path = Path

    def host_path(value):
        path = original_path(value)
        if path.is_absolute() and path.parts[1] in {"etc", "var"}:
            return host / path.relative_to("/")
        return path

    calls = []

    def command(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            stdout="192.168.49.2" if "minikube" in " ".join(args) else ""
        )

    monkeypatch.setattr(node, "Path", host_path)
    monkeypatch.setattr(node, "command", command)
    node.configure_proxy(
        {"server_ip": "203.0.113.1"},
        {"tls": {"ca": "test-ca"}, "origin_token": "test-token"},
    )
    config = (host / "etc/nginx/sites-available/wonderland").read_text()
    assert "proxy_pass https://192.168.49.2:443;" in config
    assert "proxy_ssl_verify on;" in config
    assert "proxy_ssl_name frontend;" in config
    assert "proxy_ssl_server_name on;" in config
    assert config.index("return 403") < config.index("return 204")
    assert 'proxy_set_header X-Wonderland-Gateway "";' in config
    assert ["nginx", "-t"] in calls
    assert ["systemctl", "reload", "nginx"] in calls


def test_restart_installs_routing_reconciliation_unit(node, monkeypatch, tmp_path):
    host = tmp_path / "units"
    host.mkdir()
    original_path = Path

    def host_path(value):
        if str(value).startswith("/etc/systemd/system/"):
            return host / original_path(value).name
        return original_path(value)

    calls = []
    monkeypatch.setattr(node, "Path", host_path)
    monkeypatch.setattr(node, "command", lambda args, **kw: calls.append(args))
    node.install_units(original_path("/opt/wonderland/source/node-config.json"))
    routing = (host / "wonderland-routing.service").read_text()
    assert "After=wonderland-minikube.service network-online.target" in routing
    assert "Requires=wonderland-minikube.service" in routing
    assert " routing --config /opt/wonderland/source/node-config.json" in routing
    assert "RemainAfterExit=yes" in routing
    assert any("enable" in args and "wonderland-routing" in args for args in calls)
