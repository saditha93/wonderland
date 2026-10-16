"""Prepare private runtime values, Stripe sandbox configuration and demo identities."""

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
import httpx
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import URL, make_url
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from botocore.exceptions import ClientError
from scripts.aws.workload_templates import tls_material
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    write_private_json,
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
        deployed_runtime = json.loads(
            sm.get_secret_value(SecretId=deployment_details["runtime_secret_arn"])[
                "SecretString"
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        deployed_runtime = None
    if path.exists():
        value = json.loads(path.read_text())
    elif deployed_runtime:
        value = deployed_runtime
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
    if deployed_runtime and (
        value["master"] != deployed_runtime["master"]
        or value["tls"] != deployed_runtime["tls"]
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
