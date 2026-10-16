"""Simple local MVP/infrastructure commands. No AWS account operations."""

import argparse
import fcntl
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
PYTHON = str(ROOT / ".venv/bin/python")
PORTS = (8001, 8002, 8003, 8004, 5173, 5174)


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def start_database():
    directory = ROOT / "tmp/mvp"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(
        directory / "database.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as log:
        result = subprocess.run(
            [PYTHON, "scripts/local/database.py", "start"],
            cwd=ROOT,
            stdout=log,
            stderr=log,
        )
    if result.returncode:
        raise RuntimeError("Database startup failed. See private tmp/mvp/database.log.")


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start(check=False):
    if (
        not shutil.which("npm")
        or not (ROOT / "frontend/node_modules/.bin/vite").exists()
    ):
        raise SystemExit(
            "Frontend setup is missing. Follow the one-time setup in README.md."
        )
    directory = ROOT / "tmp/mvp"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (directory / "run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(
            "Wonderland is already running. Visitor: http://localhost:5173 · Admin: http://localhost:5174"
        ) from None
    occupied = [p for p in PORTS if port_open(p)]
    if occupied:
        raise SystemExit(
            "Close the old Wonderland API/frontend terminals first. Ports in use: "
            + ", ".join(map(str, occupied))
        )
    print("Starting Wonderland…", flush=True)
    start_database()
    env = {
        **os.environ,
        "APP_ENVIRONMENT": "local",
        "APP_AUTH_MODE": "local",
        "APP_PAYMENT_PROVIDER": "local",
        "APP_DEMO_MODE": "true",
        "VITE_DEMO_MODE": "true",
        "VITE_AUTH_MODE": "local",
        "VITE_API_BASE_URL": "",
    }
    # A shell configured for remote API targets must not turn a local demo into
    # an account/network operation. Always use the native loopback services.
    for key in list(env):
        if key.startswith("API_") and key.endswith("_TARGET"):
            del env[key]
        if (
            key.endswith("_DATABASE_URL")
            or key.startswith("APP_")
            and key
            not in {
                "APP_ENVIRONMENT",
                "APP_AUTH_MODE",
                "APP_PAYMENT_PROVIDER",
                "APP_DEMO_MODE",
            }
        ):
            del env[key]
    children = []
    logs = []

    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        for name, command in [
            ("apis", [PYTHON, "scripts/local/services.py"]),
            ("visitor", ["npm", "--prefix", "frontend", "run", "dev"]),
            ("admin", ["npm", "--prefix", "frontend", "run", "dev:admin"]),
        ]:
            path = directory / f"{name}.log"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            log = os.fdopen(fd, "w")
            logs.append(log)
            children.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            )
        with httpx.Client(timeout=1, trust_env=False) as client:
            deadline = time.monotonic() + 60
            while True:
                if any(p.poll() is not None for p in children):
                    raise RuntimeError(
                        "A component stopped. See private logs in tmp/mvp/."
                    )
                try:
                    ready = all(
                        client.get(f"http://127.0.0.1:{p}/health/ready").status_code
                        == 200
                        for p in PORTS[:4]
                    )
                    ready = ready and all(
                        client.get(f"http://127.0.0.1:{p}/").status_code == 200
                        for p in PORTS[4:]
                    )
                except httpx.HTTPError:
                    ready = False
                if ready:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Startup timed out. See private logs in tmp/mvp/."
                    )
                time.sleep(0.5)
        print(
            "\nWonderland MVP is ready.\nVisitor: http://localhost:5173\nAdmin:   http://localhost:5174",
            flush=True,
        )
        accounts = json.loads((ROOT / "secrets/local.accounts.json").read_text())
        if sys.stdout.isatty() and not check:
            print("\nPrivate demo sign-in details (do not share this terminal):")
            for email in ("visitor@wonderland.local", "admin@wonderland.local"):
                account = next(a for a in accounts if a["email"] == email)
                print(f"  {email}\n  Password: {account['password']}\n")
        else:
            print(
                "Private passwords: secrets/local.accounts.json (not printed to captured output)."
            )
        print(
            "Guide: docs/local/demo.md\nStop the apps: Ctrl-C. Your data stays saved.\n",
            flush=True,
        )
        if check:
            print("Startup check passed.")
            return
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
        raise RuntimeError("A component stopped. See private logs in tmp/mvp/.")
    except KeyboardInterrupt:
        print("\nStopping Wonderland apps…", flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for log in logs:
            log.close()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        choices=[
            "start",
            "test",
            "monitoring",
            "infra",
            "infra-test",
            "infra-stop",
            "package",
        ],
        default="start",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Start, check readiness and stop without displaying passwords",
    )
    args = parser.parse_args()
    if args.action == "monitoring":
        from scripts.monitoring import start as monitoring

        monitoring()
    elif args.action.startswith("infra"):
        from scripts.local_infrastructure import main as infrastructure

        infrastructure(args.action)
    elif args.action == "package":
        from scripts.handover import create_package

        create_package()
    elif args.action == "test":
        start_database()
        run(PYTHON, "-m", "pytest", "-q")
        run("npm", "--prefix", "frontend", "run", "build")
        print("MVP tests and both frontend builds passed.")
    else:
        start(args.check)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Saved data is preserved.")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
