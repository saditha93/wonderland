"""Issue developer-only identities. No HTTP login endpoint or automatic admin identity."""

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import jwt
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wonderland_common.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--subject", default="demo-visitor")
parser.add_argument("--role", choices=["visitor", "admin"], default="visitor")
parser.add_argument("--output", type=Path)
parser.add_argument("--env-file", type=Path, default=ROOT / "secrets/local.env")
args = parser.parse_args()
load_dotenv(args.env_file)
settings = Settings()
if settings.environment not in {"local", "test"} or settings.auth_mode != "local":
    raise SystemExit("Signed local identities are disabled")
if not 1 <= len(args.subject) <= 160:
    raise SystemExit("Subject must have 1–160 characters")
now = datetime.now(timezone.utc)
token = jwt.encode(
    {
        "iss": "wonderland-local",
        "aud": "wonderland-local",
        "sub": args.subject,
        "role": args.role,
        "kind": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
    },
    settings.auth_secret.get_secret_value(),
    algorithm="HS256",
)
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(token + "\n")
    print(
        "Local token written to the specified file; expires in one hour. Never commit or share it."
    )
else:
    print(token)
