"""Upgrade ignored local configuration without replacing existing data or keys."""

import base64
import os
from pathlib import Path
import secrets
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def ensure_config(path):
    path = Path(path)
    values = dotenv_values(path)
    additions = {}
    if not values.get("APP_TICKET_PRIVATE_KEY_B64"):
        if values.get("APP_TICKET_PUBLIC_KEY_B64"):
            raise RuntimeError(
                "Public ticket key exists without private key; refusing silent key rotation"
            )
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        additions["APP_TICKET_PRIVATE_KEY_B64"] = base64.b64encode(private).decode()
        additions["APP_TICKET_PUBLIC_KEY_B64"] = base64.b64encode(public).decode()
    if not values.get("APP_TICKET_OWNER_SECRET"):
        additions["APP_TICKET_OWNER_SECRET"] = secrets.token_urlsafe(48)
    if not values.get("GATE_DATABASE_URL"):
        password = secrets.token_urlsafe(36)
        additions["LOCAL_VISITS_ROLE_PASSWORD"] = password
        url = make_url(values["MIGRATION_DATABASE_URL"]).set(
            username="wonderland_visits", password=password
        )
        additions["GATE_DATABASE_URL"] = url.render_as_string(hide_password=False)
    if additions:
        with path.open("a") as stream:
            stream.write(
                "\n" + "\n".join(f"{k}={v}" for k, v in additions.items()) + "\n"
            )
    contents = path.read_text().replace("APP_VERSION=0.2.0", "APP_VERSION=0.3.0")
    path.write_text(contents)
    os.chmod(path, 0o600)
