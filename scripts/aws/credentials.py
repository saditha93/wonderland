"""Shared credential loading and safe errors; this module never calls AWS."""

import os
from dotenv import dotenv_values


class GuardError(ValueError):
    """A configuration or safety refusal that contains no secret values."""


def load_credentials(target, root):
    """Read only cloud credentials, without importing unrelated app settings."""
    values = dotenv_values(root / ".env", interpolate=False)
    keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]
    selected = dict(values if any(values.get(k) for k in keys) else os.environ)
    if not any(selected.get(k) for k in keys):
        return {}
    if not all(selected.get(k) for k in keys[:2]):
        raise GuardError("Provide both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    region = selected.get("AWS_REGION") or selected.get("AWS_DEFAULT_REGION")
    if region and region != target["region"]:
        raise GuardError("AWS environment region must match the reviewed target")
    for key in keys:
        os.environ.pop(key, None)
        if selected.get(key):
            os.environ[key] = selected[key]
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)
    return {
        "aws_access_key_id": selected[keys[0]],
        "aws_secret_access_key": selected[keys[1]],
        "aws_session_token": selected.get(keys[2]) or None,
    }
