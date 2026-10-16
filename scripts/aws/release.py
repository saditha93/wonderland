"""Publish and verify the small AWS demo without distributing static AWS keys."""

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
import httpx
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import URL, make_url
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from botocore.exceptions import ClientError
from scripts.aws.workload_templates import tls_material, SERVICES
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    write_private_json,
    run,
    require_free_plan,
    source_fingerprint,
)


def configure_stripe(deployment_details):
    values = dotenv_values(ROOT / ".env", interpolate=False)
    key = values.get("APP_STRIPE_SECRET_KEY") or ""
    if not key.startswith("sk_test_"):
        raise GuardError("A Stripe sandbox secret key is required in .env")
    with httpx.Client(
        base_url="https://api.stripe.com/v1", auth=(key, ""), timeout=45
    ) as client:
        result = client.get("/balance")
        result.raise_for_status()
        if result.json().get("livemode") is not False:
            raise GuardError("Only Stripe test mode is allowed")
        endpoint = deployment_details["api_url"] + "/api/booking/payments/webhook"
        webhook = values.get("APP_STRIPE_WEBHOOK_SECRET") or ""
        if not webhook:
            existing = client.get("/webhook_endpoints", params={"limit": 100})
            existing.raise_for_status()
            if any(x["url"] == endpoint for x in existing.json()["data"]):
                raise GuardError(
                    "Stripe endpoint already exists; restore its signing secret in .env before continuing"
                )
            response = client.post(
                "/webhook_endpoints",
                data={
                    "url": endpoint,
                    "enabled_events[0]": "checkout.session.completed",
                    "enabled_events[1]": "checkout.session.async_payment_succeeded",
                    "description": "Wonderland AWS sandbox demo",
                },
                headers={
                    "Idempotency-Key": "wonderland-demo-"
                    + hashlib.sha256(endpoint.encode()).hexdigest()
                },
            )
            response.raise_for_status()
            event = response.json()
            if event.get("livemode") is not False:
                raise GuardError("Unexpected live webhook")
            webhook = event["secret"]
            set_key(ROOT / ".env", "APP_STRIPE_WEBHOOK_SECRET", webhook)
            (ROOT / ".env").chmod(0o600)
            write_private_json(
                PRIVATE / "stripe-endpoint.json", {"id": event["id"], "url": endpoint}
            )
        if not webhook.startswith("whsec_"):
            raise GuardError("Invalid webhook signing secret")
    return {"APP_STRIPE_SECRET_KEY": key, "APP_STRIPE_WEBHOOK_SECRET": webhook}


def prepare_runtime(aws, target_settings, deployment_details):
    path = PRIVATE / "runtime.json"
    sm = aws.client("secretsmanager")
    try:
        run_on_server = json.loads(
            sm.get_secret_value(SecretId=deployment_details["runtime_secret_arn"])[
                "SecretString"
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        run_on_server = None
    if path.exists():
        value = json.loads(path.read_text())
    elif run_on_server:
        value = run_on_server
    else:
        values = {}
        for role, key in [
            ("attractions", "ATTRACTIONS_DATABASE_URL"),
            ("booking", "BOOKING_DATABASE_URL"),
            ("visits", "GATE_DATABASE_URL"),
            ("reporting", "ANALYTICS_DATABASE_URL"),
            ("bi", "BI_DATABASE_URL"),
        ]:
            pw = secrets.token_urlsafe(36)
            values["LOCAL_" + role.upper() + "_ROLE_PASSWORD"] = pw
            values[key] = URL.create(
                "postgresql+psycopg",
                username="wonderland_" + role,
                password=pw,
                host="postgres",
                port=5432,
                database="wonderland",
            ).render_as_string(hide_password=False)
        values["LOCAL_METABASE_ROLE_PASSWORD"] = secrets.token_urlsafe(36)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        values["APP_TICKET_PRIVATE_KEY_B64"] = base64.b64encode(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        ).decode()
        values["APP_TICKET_PUBLIC_KEY_B64"] = base64.b64encode(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        ).decode()
        values["APP_TICKET_OWNER_SECRET"] = secrets.token_urlsafe(48)
        value = {
            "values": values,
            "master": {
                "username": "wonderland_owner",
                "password": secrets.token_urlsafe(36),
            },
            "tls": tls_material(["postgres"]),
            "origin_token": json.loads((PRIVATE / "origin-token.json").read_text())[
                "token"
            ],
        }
    if run_on_server and (
        value["master"] != run_on_server["master"]
        or value["tls"] != run_on_server["tls"]
    ):
        raise GuardError(
            "Private state differs from deployed database/TLS; refusing silent credential rotation"
        )
    for cert in value["tls"]["services"].values():
        expiry = x509.load_pem_x509_certificate(
            cert["tls.crt"].encode()
        ).not_valid_after_utc
        if expiry < datetime.now(timezone.utc) + timedelta(days=2):
            raise GuardError(
                "Internal demo certificates expire soon; review certificate renewal before this release"
            )
    value["values"].update(configure_stripe(deployment_details))
    write_private_json(path, value)
    sm.put_secret_value(
        SecretId=deployment_details["runtime_secret_arn"],
        SecretString=json.dumps(value),
    )
    bi = (
        make_url(value["values"]["BI_DATABASE_URL"])
        .update_query_dict(
            {"sslmode": "verify-full", "sslrootcert": "/run/rds-ca/global-bundle.pem"}
        )
        .render_as_string(hide_password=False)
    )
    reporting = PRIVATE / "reporting.env"
    reporting.write_text("BI_DATABASE_URL=" + bi + "\n")
    reporting.chmod(0o600)
    return value


def publish_images(aws, target_settings, deployment_details):
    """Build in AWS to avoid large image uploads over the local connection."""
    client = aws.client("ecr")
    missing = []
    for name in deployment_details["repositories"]:
        try:
            client.describe_images(
                repositoryName=target_settings["name"] + "/" + name,
                imageIds=[{"imageTag": target_settings["release"]}],
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ImageNotFoundException":
                raise
            missing.append(name)
    if not missing:
        return
    path = PRIVATE / "build-source.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in [
            "requirements.lock",
            ".dockerignore",
            "infrastructure/local/Dockerfile.migrate",
            "scripts/db_migrate.py",
            "scripts/cloud_migrate.py",
            "scripts/aws/image_builder.py",
        ]:
            z.write(ROOT / name, name)
        for folder in ["services", "wonderland_common", "frontend"]:
            for f in sorted((ROOT / folder).rglob("*")):
                relative = f.relative_to(ROOT)
                if not f.is_file() or any(
                    x in {"node_modules", "dist", "dist-admin", "__pycache__", ".git"}
                    for x in relative.parts
                ):
                    continue
                if (
                    f.name.startswith(".env")
                    or f.suffix in {".pyc", ".pem"}
                    and f.name != "rds-global-bundle.pem"
                ):
                    continue
                z.write(f, str(relative))
        z.writestr(
            "build-config.json",
            json.dumps(
                {
                    "target": target_settings,
                    "deployment": deployment_details,
                    "missing": missing,
                }
            ),
        )
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = "releases/" + target_settings["release"] + "/build-" + digest + ".zip"
    aws.client("s3").upload_file(
        str(path),
        deployment_details["artifact_bucket"],
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    sm = aws.client("secretsmanager")
    value = json.loads((PRIVATE / "runtime.json").read_text())
    auth = client.get_authorization_token()["authorizationData"][0]
    if (
        auth["proxyEndpoint"]
        != f"https://{target_settings['account_id']}.dkr.ecr.{target_settings['region']}.amazonaws.com"
    ):
        raise GuardError("Unexpected build registry")
    value["build_registry_auth"] = {
        k: auth[k] for k in ["authorizationToken", "proxyEndpoint"]
    }
    sm.put_secret_value(
        SecretId=deployment_details["runtime_secret_arn"],
        SecretString=json.dumps(value),
    )
    downloader = f"""import boto3,hashlib,io,zipfile,pathlib
body=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details["artifact_bucket"]!r},Key={key!r})['Body'].read()
assert hashlib.sha256(body).hexdigest()=={digest!r}
root=pathlib.Path('/opt/wonderland/build-source')
assert not root.is_symlink()
import shutil
if root.exists(): shutil.rmtree(root)
with zipfile.ZipFile(io.BytesIO(body)) as z:
 for name in z.namelist():
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
 z.extractall(root)
"""
    try:
        run_on_server(
            aws,
            deployment_details,
            [
                "set -eu",
                "umask 077",
                "for n in $(seq 1 180); do test -f /opt/wonderland/bootstrap-ready && break; sleep 5; done",
                "test -f /opt/wonderland/bootstrap-ready",
                "export DEBIAN_FRONTEND=noninteractive",
                "apt-get update -qq && apt-get install -y -qq docker.io",
                "systemctl start docker",
                "python3 -c " + shlex.quote(downloader),
                "python3 /opt/wonderland/build-source/scripts/aws/image_builder.py /opt/wonderland/build-source/build-config.json",
            ],
            timeout=2400,
        )
        for name in missing:
            client.describe_images(
                repositoryName=target_settings["name"] + "/" + name,
                imageIds=[{"imageTag": target_settings["release"]}],
            )
        print("All six immutable images verified in ECR after private on-node build.")
    finally:
        value.pop("build_registry_auth", None)
        sm.put_secret_value(
            SecretId=deployment_details["runtime_secret_arn"],
            SecretString=json.dumps(value),
        )


def run_on_server(aws, deployment_details, commands, timeout=1800, echo=True):
    ssm = aws.client("ssm")
    ready = False
    for _ in range(120):
        nodes = ssm.describe_instance_information(
            Filters=[
                {"Key": "InstanceIds", "Values": [deployment_details["instance_id"]]}
            ]
        )["InstanceInformationList"]
        if nodes and nodes[0]["PingStatus"] == "Online":
            ready = True
            break
        time.sleep(5)
    if not ready:
        raise GuardError("SSM agent is not online; inspect EC2 boot status")
    sent = ssm.send_command(
        InstanceIds=[deployment_details["instance_id"]],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands, "executionTimeout": [str(timeout)]},
        TimeoutSeconds=timeout,
    )
    cid = sent["Command"]["CommandId"]
    print("SSM operation started:", cid, flush=True)
    for n in range(timeout // 5 + 1):
        try:
            result = ssm.get_command_invocation(
                CommandId=cid, InstanceId=deployment_details["instance_id"]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "InvocationDoesNotExist":
                time.sleep(5)
                continue
            raise
        if result["Status"] in {"Success", "Failed", "TimedOut", "Cancelled"}:
            write_private_json(PRIVATE / ("ssm-" + cid + ".json"), result)
            if result["Status"] != "Success":
                raise GuardError(
                    "SSM operation "
                    + result["Status"]
                    + "; private diagnostic file saved under secrets/simple-cloud"
                )
            if echo:
                print(result.get("StandardOutputContent", ""))
            return result
        if n and n % 12 == 0:
            print("Waiting for server operation...", flush=True)
        time.sleep(5)
    raise GuardError("SSM operation did not complete within the bounded wait")


def install_workloads(aws, target_settings, deployment_details):
    path = PRIVATE / "node.zip"
    write_private_json(
        PRIVATE / "node-config.json",
        {"target": target_settings, "deployment": deployment_details},
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        files = [
            "scripts/__init__.py",
            "scripts/aws/__init__.py",
            "scripts/aws/workload_templates.py",
            "scripts/aws/workloads.py",
            "infrastructure/aws/node.py",
            "analytics/dashboard.json",
        ]
        files += [str(p.relative_to(ROOT)) for p in (ROOT / "analytics").rglob("*.sql")]
        files += [
            str(p.relative_to(ROOT))
            for folder in [
                "infrastructure/kubernetes/base",
                "infrastructure/kubernetes/local",
            ]
            for p in (ROOT / folder).glob("*.yaml")
        ]
        files += ["frontend/nginx.conf", "wonderland_common/rds-global-bundle.pem"]
        for name in files:
            archive.write(ROOT / name, name)
        archive.write(PRIVATE / "node-config.json", "node-config.json")
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = "releases/" + target_settings["release"] + "/" + digest + ".zip"
    aws.client("s3").upload_file(
        str(path),
        deployment_details["artifact_bucket"],
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    downloader = f"""import boto3,hashlib,io,zipfile,pathlib
body=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details["artifact_bucket"]!r},Key={key!r})['Body'].read()
assert hashlib.sha256(body).hexdigest()=={digest!r}
root=pathlib.Path('/opt/wonderland/source')
with zipfile.ZipFile(io.BytesIO(body)) as z:
 for name in z.namelist():
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
 z.extractall(root)
"""
    commands = [
        "set -eu",
        "umask 077",
        "for n in $(seq 1 180); do test -f /opt/wonderland/bootstrap-ready && break; sleep 5; done",
        "test -f /opt/wonderland/bootstrap-ready",
        "python3 -c " + shlex.quote(downloader),
        "python3 -m venv --clear /opt/wonderland/runtime",
        "/opt/wonderland/runtime/bin/pip install --disable-pip-version-check boto3==1.43.113 pyyaml==6.0.3 cryptography==50.0.2 sqlalchemy==2.1.4",
        "/opt/wonderland/runtime/bin/python /opt/wonderland/source/infrastructure/aws/node.py install --config /opt/wonderland/source/node-config.json",
    ]
    run_on_server(aws, deployment_details, commands)


def publish_websites(aws, target_settings, deployment_details):
    amplify = aws.client("amplify")
    jobs = {}
    for name, portal in deployment_details["portals"].items():
        response = amplify.create_deployment(appId=portal["app_id"], branchName="demo")
        jobs[name] = {k: response[k] for k in ["jobId", "zipUploadUrl"]}
        write_private_json(PRIVATE / "server-hosting-jobs.json", jobs)
    sm = aws.client("secretsmanager")
    value = json.loads((PRIVATE / "runtime.json").read_text())
    value["build_hosting_jobs"] = jobs
    sm.put_secret_value(
        SecretId=deployment_details["runtime_secret_arn"],
        SecretString=json.dumps(value),
    )
    body = (ROOT / "scripts/aws/site_builder.py").read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    key = "releases/" + target_settings["release"] + "/hosting-" + digest + ".py"
    aws.client("s3").put_object(
        Bucket=deployment_details["artifact_bucket"],
        Key=key,
        Body=body,
        ServerSideEncryption="AES256",
    )
    downloader = f"import boto3,hashlib,pathlib;b=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details['artifact_bucket']!r},Key={key!r})['Body'].read();assert hashlib.sha256(b).hexdigest()=={digest!r};pathlib.Path('/opt/wonderland/server-hosting.py').write_bytes(b)"
    try:
        run_on_server(
            aws,
            deployment_details,
            [
                "set -eu",
                "umask 077",
                "python3 -c " + shlex.quote(downloader),
                "python3 /opt/wonderland/server-hosting.py",
            ],
            timeout=600,
        )
    finally:
        value.pop("build_hosting_jobs", None)
        sm.put_secret_value(
            SecretId=deployment_details["runtime_secret_arn"],
            SecretString=json.dumps(value),
        )
    for name, portal in deployment_details["portals"].items():
        job = jobs[name]
        amplify.start_deployment(
            appId=portal["app_id"], branchName="demo", jobId=job["jobId"]
        )
        for _ in range(60):
            status = amplify.get_job(
                appId=portal["app_id"], branchName="demo", jobId=job["jobId"]
            )["job"]["summary"]["status"]
            if status == "SUCCEED":
                break
            if status in {"FAILED", "CANCELLED"}:
                raise GuardError("Amplify " + name + " publishing failed")
            time.sleep(5)
        else:
            raise GuardError("Amplify publishing timed out")
        print("Server-built Amplify portal ready:", portal["origin"])


def create_demo_accounts(aws, target_settings, deployment_details):
    path = PRIVATE / "accounts.json"
    client = aws.client("cognito-idp")
    accounts = (
        json.loads(path.read_text())
        if path.exists()
        else {
            role: {
                "email": role + "@wonderland-demo.invalid",
                "password": secrets.token_urlsafe(24) + "aA1!",
            }
            for role in ("visitor", "admin")
        }
    )
    # Save before writes so retry never loses the only copy of generated credentials.
    write_private_json(path, accounts)
    for role, account in accounts.items():
        try:
            client.admin_get_user(
                UserPoolId=deployment_details["pool_id"], Username=account["email"]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "UserNotFoundException":
                raise
            client.admin_create_user(
                UserPoolId=deployment_details["pool_id"],
                Username=account["email"],
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": account["email"]},
                    {"Name": "email_verified", "Value": "true"},
                ],
                TemporaryPassword=account["password"],
            )
            client.admin_set_user_password(
                UserPoolId=deployment_details["pool_id"],
                Username=account["email"],
                Password=account["password"],
                Permanent=True,
            )
        if role == "admin":
            client.admin_add_user_to_group(
                UserPoolId=deployment_details["pool_id"],
                Username=account["email"],
                GroupName="administrators",
            )
    print(
        "Demo logins saved privately in secrets/simple-cloud/accounts.json; no emails sent."
    )


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
            if response.headers.get("access-control-allow-origin") != portal["origin"]:
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
    evidence["demonstration_ready"] = False
    evidence["pending"] = [
        "Real sandbox checkout and signed payment webhook",
        "Cloud gate/ride rehearsal during park hours",
        "Self-service signup and real email confirmation",
        "GitHub remote CI execution",
    ]
    write_private_json(PRIVATE / "verification.json", evidence)
    print(
        "Hosting, Cognito roles, CORS, verified TLS, workload status and seven stored Metabase queries checked. Booking/Stripe checkout and gate/ride still require rehearsal."
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


def release_application(aws, target_settings, deployment_details):
    require_free_plan(aws)
    # Immutable image tags may only be reused for exactly the same source.
    store = aws.client("s3")
    key = "releases/" + target_settings["release"] + "/source.json"
    fingerprint = source_fingerprint()
    try:
        previous = json.loads(
            store.get_object(Bucket=deployment_details["artifact_bucket"], Key=key)[
                "Body"
            ].read()
        )
        if previous["sha256"] != fingerprint:
            raise GuardError(
                "This release already belongs to different source; select a new release in secrets/simple-cloud/target.json"
            )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            raise
        store.put_object(
            Bucket=deployment_details["artifact_bucket"],
            Key=key,
            Body=json.dumps({"sha256": fingerprint}).encode(),
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
        )
    prepare_runtime(aws, target_settings, deployment_details)
    publish_images(aws, target_settings, deployment_details)
    install_workloads(aws, target_settings, deployment_details)
    publish_websites(aws, target_settings, deployment_details)
    create_demo_accounts(aws, target_settings, deployment_details)
    verify_deployment(aws, target_settings, deployment_details)
