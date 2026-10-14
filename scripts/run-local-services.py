"""Start local services without Docker; stop all with Ctrl-C."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SERVICES = [
    "attractions-service",
    "booking-service",
    "gate-ride-service",
    "analytics-worker",
]
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets/local.env")
children = []


def stop(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    for port, name in enumerate(SERVICES, 8001):
        env = {**os.environ, "APP_ENVIRONMENT": "local"}
        database_key = {
            "attractions-service": "ATTRACTIONS_DATABASE_URL",
            "booking-service": "BOOKING_DATABASE_URL",
            "gate-ride-service": "GATE_DATABASE_URL",
            "analytics-worker": "ANALYTICS_DATABASE_URL",
        }.get(name)
        for key in list(env):
            if key.endswith("_DATABASE_URL") or key.startswith("LOCAL_"):
                env.pop(key, None)
        if name != "booking-service":
            for key in (
                "APP_TICKET_SECRET",
                "APP_TICKET_PRIVATE_KEY_PATH",
                "APP_TICKET_PRIVATE_KEY_B64",
                "APP_LOCAL_WEBHOOK_SECRET",
                "APP_STRIPE_SECRET_KEY",
                "APP_STRIPE_WEBHOOK_SECRET",
            ):
                env.pop(key, None)
        if name not in {"booking-service", "gate-ride-service"}:
            env.pop("APP_TICKET_OWNER_SECRET", None)
            env.pop("APP_TICKET_PUBLIC_KEY_B64", None)
            env.pop("APP_TICKET_PUBLIC_KEY_PATH", None)
        if name == "analytics-worker":
            env["APP_ANALYTICS_ENABLED"] = os.environ.get(
                "APP_ANALYTICS_ENABLED", "true"
            )
        if name not in SERVICES:
            env.pop("APP_AUTH_SECRET", None)
            env.pop("APP_AUTH_MODE", None)
        if database_key and os.environ.get(database_key):
            env["APP_DATABASE_URL"] = os.environ[database_key]
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--app-dir",
                    str(ROOT / "services" / name),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
            )
        )
    reported = set()
    while True:
        for index, child in enumerate(children):
            if child.poll() is not None and index not in reported:
                print(
                    f"{SERVICES[index]} stopped; other services continue. Inspect its logs before restarting.",
                    flush=True,
                )
                reported.add(index)
        if len(reported) == len(children):
            raise RuntimeError("All service processes stopped")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
