"""Run against live local processes or Compose; not an in-memory test."""

import json
from urllib.request import urlopen

for port, name in zip(
    range(8001, 8005),
    ["attractions-service", "booking-service", "gate-ride-service", "analytics-worker"],
):
    with urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=5) as response:
        data = json.load(response)
        assert (
            response.status == 200
            and data["status"] == "ok"
            and data["service"] == name
        )
        print(f"PASS {name}: {data['scope']}")
