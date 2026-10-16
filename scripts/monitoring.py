"""Start the private local Metabase dashboard and verify stored SQL."""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv/bin/python")


def start():
    if not shutil.which("java"):
        raise RuntimeError("Metabase needs Java 21. See docs/local/monitoring.md.")
    if not (ROOT / "tmp/metabase/metabase.jar").exists():
        raise RuntimeError(
            "Pinned Metabase JAR is missing. See docs/archive/phases/phase-4-outcome.md for download instructions."
        )
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 3000)) == 0:
            raise RuntimeError(
                "Port 3000 is already in use. Use the existing Metabase terminal, or close it before starting another copy."
            )
    # Native setup preserves existing keys/data and prepares the read-only BI role.
    from mvp import start_database

    start_database()
    directory = ROOT / "tmp/metabase"
    fd = os.open(directory / "runner.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)

    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    with os.fdopen(fd, "w") as log:
        process = subprocess.Popen(
            [PYTHON, "scripts/run-metabase.py"],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            start_new_session=True,
            umask=0o077,
        )
        try:
            print("Starting Metabase… first startup may take a minute.", flush=True)
            with httpx.Client(timeout=2, trust_env=False) as client:
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Metabase stopped. Inspect private tmp/metabase/runner.log."
                        )
                    try:
                        if (
                            client.get("http://127.0.0.1:3000/api/health").status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError(
                        "Metabase startup timed out. Inspect private tmp/metabase/runner.log."
                    )
            subprocess.run(
                [PYTHON, "scripts/provision-metabase.py"], cwd=ROOT, check=True
            )
            config = json.loads((ROOT / "secrets/metabase.json").read_text())
            print(
                f"\nAssignment dashboard: http://localhost:3000/dashboard/{config['dashboard_id']}",
                flush=True,
            )
            if sys.stdout.isatty():
                print(
                    f"Private Metabase login:\nEmail: {config['email']}\nPassword: {config['password']}"
                )
            else:
                print(
                    "Private login: secrets/metabase.json (credentials not printed to captured output)."
                )
            print(
                "Keep this terminal open. Ctrl-C stops Metabase; the app and saved data remain.",
                flush=True,
            )
            process.wait()
            raise RuntimeError("Metabase stopped. See its private runner log.")
        except KeyboardInterrupt:
            print("\nStopping Metabase…", flush=True)
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
