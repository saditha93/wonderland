"""Simple local infrastructure rehearsal. Never invokes account/deploy tools."""

from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import signal
import socket
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv/bin/python")
LOCAL = [PYTHON, "scripts/local-kubernetes.py"]
EVIDENCE = ROOT / "docs/evidence/local-infrastructure.json"


def stop_process(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


class Rehearsal:
    def __init__(self, record=True):
        self.record = record
        self.directory = ROOT / "tmp/infrastructure"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_CLI_ARGS"))}
        self.env["AWS_EC2_METADATA_DISABLED"] = "true"
        if record and EVIDENCE.exists():
            previous = json.loads(EVIDENCE.read_text())
            stamp = re.sub(r"\D", "", previous["started_at"])
            archived = EVIDENCE.with_name(f"local-infrastructure-{stamp}.json")
            if not archived.exists():
                archived.write_text(json.dumps(previous, indent=2) + "\n")
        self.summary = {"started_at": datetime.now(ZoneInfo("Asia/Colombo")).isoformat(),
                        "scope": "local Minikube + offline Terraform mocks; no AWS account calls",
                        "status": "running", "steps": []}
        from handover import allowed, source_files

        sources = source_files(ROOT)

        digest = hashlib.sha256()
        for relative in sources:
            path = ROOT / relative
            if allowed(relative) and not relative.startswith("docs/") and path.is_file() and not path.is_symlink():
                digest.update(relative.encode() + b"\0" + path.read_bytes())
        self.summary["source_sha256"] = digest.hexdigest()
        self.save()

    def save(self):
        if self.record:
            EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE.write_text(json.dumps(self.summary, indent=2) + "\n")

    def run(self, label, command, timeout=900):
        print(f"→ {label}", flush=True)
        step = {"name": label, "status": "running"}
        self.summary["steps"].append(step)
        self.save()
        path = self.directory / f"{len(self.summary['steps']):02d}.log"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        started = time.monotonic()
        try:
            with os.fdopen(fd, "w") as log:
                process = subprocess.Popen(command, cwd=ROOT, env=self.env, stdout=log, stderr=log, start_new_session=True)
                try:
                    code = process.wait(timeout=timeout)
                except BaseException:
                    stop_process(process)
                    raise
            step["status"] = "passed" if code == 0 else "failed"
            step["exit_code"] = code
            # Only intentionally public pass/load summaries enter the evidence.
            step["observations"] = [line[:500] for line in path.read_text(errors="replace").splitlines()
                                    if line.startswith(("PASS ", "Catalog load:", "All four Terraform roots"))]
            if code:
                raise RuntimeError(f"{label} failed. Private log: {path.relative_to(ROOT)}")
            print(f"  Passed ({time.monotonic() - started:.0f}s)", flush=True)
        except BaseException:
            if step["status"] == "running":
                step["status"] = "interrupted"
            raise
        finally:
            step["seconds"] = round(time.monotonic() - started, 2)
            self.save()

    def prepare(self):
        for executable in ("colima", "docker", "minikube", "kubectl"):
            if not shutil.which(executable):
                raise RuntimeError(f"Missing {executable}. See docs/local-kubernetes.md for first-machine setup.")
        for port in (5180, 5181):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Close the old infrastructure/port-forward terminal first; this command starts its own gateway.")
        self.run("Start local VM", ["colima", "start", "--profile", "wonderland", "--cpu", "4", "--memory", "6", "--disk", "30", "--runtime", "docker", "--vm-type", "vz"])
        self.run("Start local Kubernetes", [*LOCAL, "start"])
        self.run("Build and load application images", [*LOCAL, "build"], timeout=1800)
        self.run("Deploy database, migrations and apps", [*LOCAL, "deploy"])

    def forward(self):
        path = self.directory / "gateway.log"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as log:
            process = subprocess.Popen([*LOCAL, "forward"], cwd=ROOT, env=self.env, stdout=log, stderr=log, start_new_session=True)
        try:
            with httpx.Client(timeout=2, trust_env=False) as client:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Gateway stopped. Inspect private tmp/infrastructure/gateway.log.")
                    try:
                        if all(client.get(f"http://127.0.0.1:{port}/health").status_code == 200 for port in (5180, 5181)):
                            return process
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
            raise RuntimeError("Local gateway did not become ready")
        except BaseException:
            stop_process(process)
            raise


def main(action):
    directory = ROOT / "tmp/infrastructure"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Infrastructure is already running/testing. Stop that terminal with Ctrl-C first.") from None
        rehearsal = Rehearsal(record=action == "infra-test")
        def interrupted(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        forward = None
        deployed = False
        try:
            if action == "infra-stop":
                rehearsal.run("Stop local Kubernetes (keep data)", [*LOCAL, "stop"])
                rehearsal.run("Stop local VM (keep data)", ["colima", "stop", "--profile", "wonderland"])
                print("Local infrastructure stopped. Database volumes and images preserved.")
                return
            if action == "infra-test":
                rehearsal.run("Validate Terraform offline and execute mocked plans", [PYTHON, "scripts/validate-cloud.py"])
            rehearsal.prepare()
            deployed = True
            forward = rehearsal.forward()
            if action == "infra":
                print("\nLocal infrastructure is ready.\nVisitor: http://localhost:5180\nAdmin:   http://localhost:5181", flush=True)
                if sys.stdout.isatty():
                    accounts = json.loads((ROOT / "secrets/kubernetes.accounts.json").read_text())
                    print("Private cluster passwords (do not share):")
                    for email in ("visitor@wonderland.local", "admin@wonderland.local"):
                        account = next(a for a in accounts if a["email"] == email)
                        print(f"{email}\nPassword: {account['password']}\n")
                print("Ctrl-C closes the gateway. ./start.sh infra-stop stops the VM and cluster.", flush=True)
                while forward.poll() is None:
                    time.sleep(0.5)
                raise RuntimeError("Gateway stopped; restart ./start.sh infra.")
            rehearsal.run("Verify workloads, storage and metrics", [*LOCAL, "verify"])
            scenario = "local-" + str(int(time.time()))
            rehearsal.run("End-to-end booking, admin and analytics", [PYTHON, "scripts/smoke-kubernetes.py", "--scenario", scenario])
            for demo, title in [("self-heal", "Pod self-healing"), ("blue-green", "Blue-green switch and rollback"), ("recovery", "Worker failure and queue recovery"), ("readiness", "Database failure, readiness and persistence"), ("autoscale", "Real HTTP load and HPA scale-up/down")]:
                rehearsal.run(title, [PYTHON, "scripts/demo-kubernetes.py", demo])
            rehearsal.run("Final workload verification", [*LOCAL, "verify"])
            rehearsal.run("Final source/report reconciliation", [PYTHON, "scripts/smoke-kubernetes.py", "--scenario", scenario])
            rehearsal.summary["status"] = "passed"
            print("\nAll local infrastructure tests passed. Evidence: docs/evidence/local-infrastructure.json\nNo AWS deployment was performed. Stop the cluster when finished: ./start.sh infra-stop", flush=True)
        except (Exception, KeyboardInterrupt):
            rehearsal.summary["status"] = "failed"
            if deployed and action == "infra-test":
                print("Restoring the local deployment baseline…", flush=True)
                try:
                    rehearsal.run("Restore baseline after failed/interrupted test", [*LOCAL, "deploy"])
                except (Exception, KeyboardInterrupt):
                    print("Restoration needs attention. See private logs; do not treat this run as passed.", flush=True)
            raise
        finally:
            if forward:
                stop_process(forward)
            rehearsal.summary["finished_at"] = datetime.now(ZoneInfo("Asia/Colombo")).isoformat()
            rehearsal.save()
