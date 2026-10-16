"""Create private local credentials once; only password hashes reach services."""

import json
import os
from pathlib import Path
import secrets

from dotenv import dotenv_values
from wonderland_common.local_login import password_hash


def ensure_accounts(env_file: Path):
    values = dotenv_values(env_file)
    if (
        values.get("APP_ENVIRONMENT") not in {"local", "test"}
        or values.get("APP_AUTH_MODE") != "local"
    ):
        raise ValueError("Local account setup requires local/test identity mode")
    credentials_file = env_file.with_suffix(".accounts.json")
    if values.get("APP_LOCAL_ACCOUNTS_JSON"):
        if not credentials_file.exists():
            raise RuntimeError(
                "Local accounts already configured but private credential file is missing; restore it instead of silently rotating passwords"
            )
        return credentials_file
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = [
            {
                "email": email,
                "subject": subject,
                "role": role,
                "password": secrets.token_urlsafe(24),
            }
            for email, subject, role in [
                ("visitor@wonderland.local", "demo-visitor", "visitor"),
                ("admin@wonderland.local", "demo-admin", "admin"),
                ("gate-test@wonderland.local", "phase3-demo-visitor", "visitor"),
                ("other@wonderland.local", "another-visitor", "visitor"),
                ("kube-test@wonderland.local", "phase5-demo-visitor", "visitor"),
            ]
        ]
        fd = os.open(credentials_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(credentials, stream, indent=2)
            stream.write("\n")
    accounts = {
        row["email"]: {
            "subject": row["subject"],
            "role": row["role"],
            "password_hash": password_hash(row["password"]),
        }
        for row in credentials
    }
    with env_file.open("a") as stream:
        stream.write(
            "\nAPP_LOCAL_ACCOUNTS_JSON='"
            + json.dumps(accounts, separators=(",", ":"))
            + "'\n"
        )
    os.chmod(credentials_file, 0o600)
    os.chmod(env_file, 0o600)
    return credentials_file
