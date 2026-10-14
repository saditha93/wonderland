"""Bounded failure and release demonstrations on the guarded local cluster only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "local_kubernetes", ROOT / "scripts/local-kubernetes.py"
)
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)
BASE = "http://127.0.0.1:5180"


def get(resource, *args):
    return json.loads(
        k.kubectl("get", resource, *args, "-o", "json", capture_output=True).stdout
    )


def wait_for(check, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(2)
    raise RuntimeError("Timed out waiting for the demonstrated condition")


def ready():
    try:
        return all(
            httpx.get(BASE + f"/api/{s}/health/ready", timeout=5).status_code == 200
            for s in ("attractions", "booking", "gate", "analytics")
        )
    except httpx.HTTPError:
        return False


def pg(sql):
    return k.kubectl(
        "exec",
        "postgres-0",
        "--",
        "psql",
        "-U",
        "wonderland_owner",
        "-d",
        "wonderland",
        "-tAc",
        sql,
        capture_output=True,
    ).stdout.strip()


def self_heal():
    selector = "app=attractions-service,color=blue"
    pods = get("pods", "-l", selector)["items"]
    victim = pods[0]
    old_uids = {p["metadata"]["uid"] for p in pods}
    k.kubectl("delete", "pod", victim["metadata"]["name"], "--wait=false")
    successes = 0
    for _ in range(20):
        r = httpx.get(BASE + "/api/attractions/attractions", timeout=10)
        assert r.status_code == 200
        successes += 1
        time.sleep(0.15)
    k.kubectl(
        "rollout", "status", "deployment/attractions-service-blue", "--timeout=120s"
    )
    current = get("pods", "-l", selector)["items"]
    new = [
        p
        for p in current
        if p["metadata"]["uid"] not in old_uids
        and not p["metadata"].get("deletionTimestamp")
    ]
    assert new
    print(
        f"PASS self-heal: replacement pod ready; {successes}/20 catalog requests succeeded during replacement"
    )


def readiness():
    before = pg("SELECT count(*) FROM booking.bookings;")
    pods = get("pods", "-l", "app=attractions-service,color=blue")["items"]
    pod = next(
        p["metadata"]["name"]
        for p in pods
        if not p["metadata"].get("deletionTimestamp")
    )
    code = "import json,urllib.request,urllib.error; result={}\nfor scope in ('live','ready'):\n try: result[scope]=urllib.request.urlopen('http://127.0.0.1:8000/health/'+scope,timeout=8).status\n except urllib.error.HTTPError as e: result[scope]=e.code\nprint(json.dumps(result))"
    try:
        k.kubectl("scale", "statefulset/postgres", "--replicas=0")
        k.kubectl("wait", "--for=delete", "pod/postgres-0", "--timeout=90s")
        result = json.loads(
            k.kubectl(
                "exec", pod, "--", "python", "-c", code, capture_output=True
            ).stdout
        )
        assert result == {"live": 200, "ready": 503}

        def removed():
            slices = get(
                "endpointslices", "-l", "kubernetes.io/service-name=attractions-service"
            )["items"]
            return not any(
                ep.get("conditions", {}).get("ready", False)
                for s in slices
                for ep in s.get("endpoints", [])
            )

        wait_for(removed, 45)
        assert httpx.get(BASE + "/health").status_code == 200
        print(
            "PASS DB outage: API liveness 200, readiness 503; unready endpoints removed; frontend process remains healthy"
        )
    finally:
        k.kubectl("scale", "statefulset/postgres", "--replicas=1")
        k.kubectl("rollout", "status", "statefulset/postgres", "--timeout=180s")
        wait_for(ready, 120)
    assert pg("SELECT count(*) FROM booking.bookings;") == before
    print(
        "PASS readiness recovery and persistent booking count after PostgreSQL restart"
    )


def blue_green():
    k.kubectl("apply", "-f", "infrastructure/kubernetes/demos/attractions-green.yaml")
    k.kubectl(
        "rollout", "status", "deployment/attractions-service-green", "--timeout=120s"
    )

    def select(color):
        k.kubectl(
            "patch",
            "service/attractions-service",
            "--type=merge",
            "-p",
            json.dumps(
                {"spec": {"selector": {"app": "attractions-service", "color": color}}}
            ),
        )

    def version(expected):
        try:
            return all(
                httpx.get(BASE + "/api/attractions/health", timeout=5).json()["version"]
                == expected
                for _ in range(5)
            )
        except (httpx.HTTPError, KeyError, ValueError):
            return False

    try:
        select("green")
        wait_for(lambda: version("0.5.1"), 45)
        assert httpx.get(BASE + "/api/attractions/attractions").status_code == 200
        print(
            "PASS green selector switch: release metadata 0.5.1 served; catalog remains available"
        )
    finally:
        select("blue")
        wait_for(lambda: version("0.5.0"), 45)
        k.kubectl("scale", "deployment/attractions-service-green", "--replicas=0")
    print(
        "PASS rollback to blue 0.5.0; green scaled to zero. Domain code is identical in both demo releases."
    )


def recovery():
    try:
        k.kubectl("scale", "deployment/analytics-worker", "--replicas=0")
        k.kubectl(
            "wait", "--for=delete", "pod", "-l", "app=analytics-worker", "--timeout=90s"
        )
        scenario = "recover-" + str(int(time.time()))
        k.run(
            [
                sys.executable,
                "scripts/smoke-kubernetes.py",
                "--scenario",
                scenario,
                "--skip-analytics",
            ]
        )
        pending = int(
            pg(
                "SELECT (SELECT count(*) FROM booking.outbox WHERE published_at IS NULL)+(SELECT count(*) FROM visits.outbox WHERE published_at IS NULL);"
            )
        )
        assert pending >= 3
        print(
            f"PASS isolated worker outage: booking/gate/rides succeeded; {pending} events durably awaiting publication"
        )
    finally:
        k.kubectl("scale", "deployment/analytics-worker", "--replicas=1")
        k.kubectl("rollout", "status", "deployment/analytics-worker", "--timeout=120s")
    k.run([sys.executable, "scripts/smoke-kubernetes.py", "--scenario", scenario])
    print(
        "PASS restarted worker drains backlog without duplicate arrival/ride or purchase counts"
    )


def autoscale():
    # Real bounded HTTP load against the catalog; no synthetic CPU-burn endpoint.
    k.kubectl("top", "pods", "-l", "app=attractions-service,color=blue")
    wait_for(
        lambda: get("deployment/attractions-service-blue")["spec"]["replicas"] == 2, 240
    )
    before = 2
    finish = time.monotonic() + 100
    counts = []

    def load(_):
        ok = bad = 0
        with httpx.Client(base_url=BASE, timeout=10) as client:
            while time.monotonic() < finish:
                try:
                    if client.get("/api/attractions/attractions").status_code == 200:
                        ok += 1
                    else:
                        bad += 1
                except httpx.HTTPError:
                    bad += 1
        return ok, bad

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(load, i) for i in range(16)]
        maximum = before
        while time.monotonic() < finish:
            observed = get("hpa/attractions-blue")["status"]
            maximum = max(
                maximum,
                observed.get("currentReplicas", 0),
                observed.get("desiredReplicas", 0),
            )
            time.sleep(5)
        counts = [f.result() for f in futures]
    print(
        f"Catalog load: {sum(c[0] for c in counts)} successful, {sum(c[1] for c in counts)} failed requests; max HPA desired/current replicas {maximum}"
    )
    wait_for(
        lambda: (
            get("deployment/attractions-service-blue")["status"].get("readyReplicas", 0)
            >= 3
        ),
        90,
    )
    observed = get("hpa/attractions-blue")["status"]
    assert observed.get("currentReplicas", 0) >= 3
    print(
        "PASS CPU HPA scaled catalog from 2 to 3 ready replicas using actual HTTP traffic"
    )
    wait_for(
        lambda: get("deployment/attractions-service-blue")["spec"]["replicas"] == 2, 240
    )
    print("PASS HPA returned to 2 replicas after load stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario",
        choices=["self-heal", "readiness", "blue-green", "recovery", "autoscale"],
    )
    args = parser.parse_args()
    k.guard()
    if not ready():
        raise SystemExit("All local services and the port-forward must be ready first")
    {
        "self-heal": self_heal,
        "readiness": readiness,
        "blue-green": blue_green,
        "recovery": recovery,
        "autoscale": autoscale,
    }[args.scenario]()
