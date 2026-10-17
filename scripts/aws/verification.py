"""Verify hosted platform behavior and privately query Metabase."""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import httpx
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    write_private_json,
    run,
)


from scripts.aws.remote import run_on_server


def verify_deployment(aws, target_settings, deployment_details):
    evidence = {"checked_at": int(time.time()), "checks": []}
    with httpx.Client(timeout=45) as client:
        for name, portal in deployment_details["portals"].items():
            response = client.get(portal["origin"])
            response.raise_for_status()
            if '<div id="root">' not in response.text:
                raise GuardError(name + " frontend HTML missing")
            evidence["checks"].append(name + " HTTPS hosting")
        for name, portal in deployment_details["portals"].items():
            response = client.options(
                deployment_details["api_url"] + "/api/attractions/attractions",
                headers={
                    "Origin": portal["origin"],
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            if (
                not response.is_success
                or response.headers.get("access-control-allow-origin")
                != portal["origin"]
            ):
                raise GuardError(name + " CORS failed")
            evidence["checks"].append(name + " CORS")
        response = client.options(
            deployment_details["api_url"] + "/api/attractions/attractions",
            headers={
                "Origin": "https://unapproved.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )
        if response.headers.get("access-control-allow-origin"):
            raise GuardError("Unapproved CORS origin accepted")
        response = client.get(
            "https://"
            + deployment_details["server_ip"]
            + "/api/attractions/attractions"
        )
        if response.status_code != 403:
            raise GuardError("Direct server origin is not protected")
        evidence["checks"] += [
            "Unapproved CORS origin denied",
            "Verified public IP TLS",
            "Direct API origin denied",
        ]
        for service in ["attractions", "booking", "gate", "analytics"]:
            response = client.get(
                deployment_details["api_url"] + "/api/" + service + "/health"
            )
            response.raise_for_status()
        evidence["checks"].append("All four APIs healthy through Minikube Ingress")
        for path in ["attractions/attractions", "booking/ticket-tiers"]:
            response = client.get(deployment_details["api_url"] + "/api/" + path)
            response.raise_for_status()
            if not response.json():
                raise GuardError("Seeded catalog/ticket tiers missing")
        evidence["checks"].append("Public seeded catalog and ticket tiers")
        response = client.get(deployment_details["api_url"] + "/api/booking/bookings")
        if response.status_code != 401:
            raise GuardError("Unauthenticated booking history accepted")
        accounts = json.loads((PRIVATE / "accounts.json").read_text())
        cognito = aws.client("cognito-idp")
        for role, account in accounts.items():
            auth = cognito.initiate_auth(
                ClientId=deployment_details["client_id"],
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": account["email"],
                    "PASSWORD": account["password"],
                },
            )
            token = auth["AuthenticationResult"]["AccessToken"]
            headers = {"Authorization": "Bearer " + token}
            identity = client.get(
                deployment_details["api_url"] + "/api/booking/identity", headers=headers
            )
            identity.raise_for_status()
            if identity.json()["role"] != role or identity.json()["mode"] != "cognito":
                raise GuardError("Cognito role mapping differs")
            protected = client.get(
                deployment_details["api_url"] + "/api/booking/admin/sales",
                headers=headers,
            )
            if protected.status_code != (200 if role == "admin" else 403):
                raise GuardError("Admin authorization check failed")
            evidence["checks"].append(
                "Cognito " + role + " login and protected admin authorization"
            )
    run_on_server(
        aws,
        deployment_details,
        [
            "/opt/wonderland/runtime/bin/python /opt/wonderland/source/infrastructure/aws/node.py status --config /opt/wonderland/source/node-config.json"
        ],
    )
    verify_metabase(aws, target_settings, deployment_details)
    evidence["checks"].append("Seven stored Metabase SQL cards over private SSM tunnel")
    evidence["scope"] = "Hosted platform, authorization and reporting query checks"
    evidence["manual_walkthrough"] = [
        "Real sandbox checkout and signed payment webhook",
        "Cloud gate/ride rehearsal during park hours",
        "Self-service signup and real email confirmation",
    ]
    write_private_json(PRIVATE / "verification.json", evidence)
    print(
        "Platform checks passed: hosting, Cognito roles, CORS, TLS, workloads and seven Metabase SQL cards. Follow docs/demo.md for this deployment's payment, gate and ride walkthrough."
    )


def verify_metabase(aws, target_settings, deployment_details):
    if not shutil.which("session-manager-plugin"):
        raise GuardError(
            "Install the official AWS Session Manager plugin to verify private Metabase"
        )
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 3001))
    except OSError:
        raise GuardError(
            "Port 3001 is occupied; close the existing monitoring tunnel before verify"
        ) from None
    finally:
        probe.close()
    log = PRIVATE / "monitoring-tunnel.log"
    with log.open("w") as stream:
        log.chmod(0o600)
        process = subprocess.Popen(
            [
                "aws",
                "ssm",
                "start-session",
                "--region",
                target_settings["region"],
                "--target",
                deployment_details["instance_id"],
                "--document-name",
                "AWS-StartPortForwardingSession",
                "--parameters",
                json.dumps({"portNumber": ["3000"], "localPortNumber": ["3001"]}),
            ],
            cwd=ROOT,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
        try:
            for _ in range(90):
                if process.poll() is not None:
                    raise GuardError(
                        "Private Metabase tunnel failed; inspect its private log"
                    )
                try:
                    response = httpx.get("http://127.0.0.1:3001/api/health", timeout=3)
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(2)
            else:
                raise GuardError("Metabase did not become ready through SSM")
            run(
                [
                    sys.executable,
                    "scripts/provision-metabase.py",
                    "--env-file",
                    str(PRIVATE / "reporting.env"),
                    "--allow-ec2-reporting",
                    "--metabase-url",
                    "http://127.0.0.1:3001",
                ]
            )
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)


def open_monitoring_tunnel(aws, target_settings, deployment_details):
    if not shutil.which("session-manager-plugin"):
        raise GuardError(
            "Install the official AWS Session Manager plugin before opening the private tunnel"
        )
    print(
        "Opening private Metabase tunnel: http://127.0.0.1:3001 (Ctrl+C closes tunnel)",
        flush=True,
    )
    run(
        [
            "aws",
            "ssm",
            "start-session",
            "--region",
            target_settings["region"],
            "--target",
            deployment_details["instance_id"],
            "--document-name",
            "AWS-StartPortForwardingSession",
            "--parameters",
            json.dumps({"portNumber": ["3000"], "localPortNumber": ["3001"]}),
        ]
    )
