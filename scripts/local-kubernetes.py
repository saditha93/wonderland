"""Manage only the named local Minikube profile and Wonderland namespace.

Credentials are sent on stdin, never kubectl CLI args or rendered stdout.
Cloud contexts and default kubeconfig are never used. No PVC deletion command.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "wonderland"
CONFIG = ROOT / "secrets/minikube.kubeconfig"
ENVFILE = ROOT / "secrets/kubernetes.env"
DOCKER_CONTEXT = "colima-wonderland"
ENV = {**os.environ, "KUBECONFIG": str(CONFIG), "DOCKER_CONTEXT": DOCKER_CONTEXT}


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, env=ENV, check=True, text=True, **kwargs)


def kubectl(*args, **kwargs):
    return run(
        [
            "kubectl",
            "--kubeconfig",
            str(CONFIG),
            "--context",
            PROFILE,
            "--namespace",
            PROFILE,
            *args,
        ],
        **kwargs,
    )


def guard():
    if not CONFIG.exists():
        raise SystemExit("Start the named local cluster first")
    config = yaml.safe_load(CONFIG.read_text())
    context = next(
        (c["context"] for c in config["contexts"] if c["name"] == PROFILE), None
    )
    if not context:
        raise SystemExit("Dedicated local context is missing")
    cluster = next(
        c["cluster"] for c in config["clusters"] if c["name"] == context["cluster"]
    )
    host = urlparse(cluster["server"]).hostname
    ip = run(["minikube", "-p", PROFILE, "ip"], capture_output=True).stdout.strip()
    profile = json.loads(
        (Path.home() / ".minikube/profiles" / PROFILE / "config.json").read_text()
    )
    if profile.get("Driver") != "docker" or host not in {"127.0.0.1", "localhost", ip}:
        raise SystemExit("Refusing a non-local Minikube context")


def configure():
    run([sys.executable, "scripts/configure-compose.py", "--output", str(ENVFILE)])
    values = dotenv_values(ENVFILE)
    from sqlalchemy.engine import make_url

    for key in [
        "MIGRATION_DATABASE_URL",
        "ATTRACTIONS_DATABASE_URL",
        "BOOKING_DATABASE_URL",
        "GATE_DATABASE_URL",
        "ANALYTICS_DATABASE_URL",
    ]:
        if make_url(values[key]).host != "postgres":
            raise SystemExit("Only in-cluster PostgreSQL URLs allowed")
    return values


def secrets_manifest(values):
    groups = {
        "postgres-admin": {"password": values["POSTGRES_PASSWORD"]},
        "auth-secret": {"signing-secret": values["APP_AUTH_SECRET"]},
        "attractions-db": {"database-url": values["ATTRACTIONS_DATABASE_URL"]},
        "booking-db": {"database-url": values["BOOKING_DATABASE_URL"]},
        "visits-db": {"database-url": values["GATE_DATABASE_URL"]},
        "reporting-db": {"database-url": values["ANALYTICS_DATABASE_URL"]},
        "booking-ticket": {"private-key": values["APP_TICKET_PRIVATE_KEY_B64"]},
        "gate-ticket": {"public-key": values["APP_TICKET_PUBLIC_KEY_B64"]},
        "ticket-owner": {"owner-secret": values["APP_TICKET_OWNER_SECRET"]},
        "booking-payment": {"webhook-secret": values["APP_LOCAL_WEBHOOK_SECRET"]},
        "migration-config": {
            k: v
            for k, v in values.items()
            if k == "MIGRATION_DATABASE_URL" or k.startswith("LOCAL_")
        },
    }
    return yaml.safe_dump_all(
        [
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": name, "namespace": PROFILE},
                "type": "Opaque",
                "stringData": data,
            }
            for name, data in groups.items()
        ],
        sort_keys=False,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["start", "build", "deploy", "verify", "forward", "stop"]
    )
    args = parser.parse_args()
    if args.action == "start":
        CONFIG.parent.mkdir(exist_ok=True, mode=0o700)
        run(
            [
                "minikube",
                "start",
                "-p",
                PROFILE,
                "--driver=docker",
                "--container-runtime=containerd",
                "--kubernetes-version=v1.37.0",
                "--memory=4096",
                "--cpus=3",
            ]
        )
        os.chmod(CONFIG, 0o600)
        run(["minikube", "-p", PROFILE, "addons", "enable", "metrics-server"])
        return
    guard()
    if args.action == "build":
        targets = {
            name: f"services/{name}/Dockerfile"
            for name in [
                "attractions-service",
                "booking-service",
                "gate-ride-service",
                "analytics-worker",
            ]
        }
        targets.update(
            migrate="infrastructure/local/Dockerfile.migrate",
            frontend="frontend/Dockerfile.kubernetes",
        )
        for name, dockerfile in targets.items():
            context = "frontend" if name == "frontend" else "."
            run(
                [
                    "docker",
                    "--context",
                    DOCKER_CONTEXT,
                    "build",
                    "-f",
                    dockerfile,
                    "-t",
                    f"wonderland/{name}:0.5.0",
                    context,
                ]
            )
            run(
                ["minikube", "-p", PROFILE, "image", "load", f"wonderland/{name}:0.5.0"]
            )
        # Metadata release for selector-switch demonstration; identical domain code.
        run(
            [
                "docker",
                "--context",
                DOCKER_CONTEXT,
                "tag",
                "wonderland/attractions-service:0.5.0",
                "wonderland/attractions-service:0.5.1",
            ]
        )
        run(
            [
                "minikube",
                "-p",
                PROFILE,
                "image",
                "load",
                "wonderland/attractions-service:0.5.1",
            ]
        )
    elif args.action == "deploy":
        values = configure()
        kubectl("apply", "-f", "infrastructure/kubernetes/base/namespace.yaml")
        # server-side apply avoids kubectl's last-applied secret annotation.
        kubectl(
            "apply",
            "--server-side",
            "--field-manager=wonderland-local",
            "-f",
            "-",
            input=secrets_manifest(values),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        kubectl("apply", "-f", "infrastructure/kubernetes/local/config.yaml")
        kubectl("apply", "-f", "infrastructure/kubernetes/local/postgres.yaml")
        kubectl("rollout", "status", "statefulset/postgres", "--timeout=180s")
        # Idempotent SQL; a successful versioned Job is reused on repeated deploys.
        kubectl("apply", "-f", "infrastructure/kubernetes/local/migrate.yaml")
        kubectl(
            "wait",
            "--for=condition=complete",
            "job/schema-migrate-v5",
            "--timeout=180s",
        )
        kubectl("apply", "-k", "infrastructure/kubernetes/local")
        for name in [
            "attractions-service-blue",
            "booking-service",
            "gate-ride-service",
            "analytics-worker",
            "frontend",
        ]:
            kubectl("rollout", "status", "deployment/" + name, "--timeout=180s")
    elif args.action == "verify":
        kubectl("get", "pods,services,hpa,pvc")
        kubectl("top", "pods")
    elif args.action == "forward":
        kubectl("port-forward", "--address=127.0.0.1", "service/frontend", "5180:8080")
    elif args.action == "stop":
        run(["minikube", "-p", PROFILE, "stop"])
        print(
            "Named cluster stopped; persistent demo volume retained. Colima VM can be stopped separately."
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        # Stderr for secret application may include sensitive request data.
        raise SystemExit(
            f"Local Kubernetes command failed (exit {exc.returncode}); no credential payload printed"
        ) from None
