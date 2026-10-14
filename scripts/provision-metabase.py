"""Provision local Metabase with read-only reporting SQL; verify every card.

Reruns reuse named database/dashboard/cards. Credentials and provisioning IDs
are stored only in ignored mode-0600 secrets/metabase.json. Does not publish a
public dashboard. Only loopback Metabase is allowed.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import secrets
import httpx
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--env-file", type=Path, default=ROOT / "secrets/local.env")
parser.add_argument(
    "--database-host", help="Use postgres for the Docker analytics profile"
)
parser.add_argument(
    "--allow-cloud-reporting",
    action="store_true",
    help="Only after the separately approved cloud deployment",
)
parser.add_argument("--metabase-url", default="http://127.0.0.1:3000")
args = parser.parse_args()
address = urlparse(args.metabase_url)
if (
    address.scheme != "http"
    or address.hostname not in {"127.0.0.1", "localhost"}
    or address.username
    or address.query
):
    raise SystemExit(
        "Metabase API must use the local encrypted-Kubernetes port-forward or native loopback"
    )
values = dotenv_values(args.env_file)
url = make_url(values["BI_DATABASE_URL"])
allowed_host = url.host in {"127.0.0.1", "localhost", "postgres"}
if args.allow_cloud_reporting:
    allowed_host = bool(
        url.host
        and url.host.endswith(".rds.amazonaws.com")
        and url.query.get("sslmode") == "verify-full"
    )
if args.database_host and (
    args.database_host not in {url.host, "postgres"}
    or (args.allow_cloud_reporting and args.database_host != url.host)
):
    raise SystemExit("Database-host override refused")
if url.username != "wonderland_bi" or not allowed_host:
    raise SystemExit("Refusing a non-project reporting database")
private = ROOT / (
    "secrets/metabase-cloud.json"
    if args.allow_cloud_reporting
    else "secrets/metabase.json"
)
config = (
    json.loads(private.read_text())
    if private.exists()
    else {
        "email": "admin@wonderland.local",
        "password": secrets.token_urlsafe(36) + "aA1!",
    }
)


def save():
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(config, stream, indent=2)
    os.chmod(private, 0o600)


save()
client = httpx.Client(base_url=args.metabase_url, timeout=120)


def request(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_error:
        # Metabase errors may contain connection details; don't echo responses.
        raise SystemExit(
            f"Metabase {method} {path} failed: HTTP {response.status_code}; inspect locally without sharing credentials"
        )
    return response.json() if response.content else None


properties = request("GET", "/api/session/properties")
if not properties.get("has-user-setup") and properties.get("setup-token"):
    request(
        "POST",
        "/api/setup",
        json={
            "token": properties["setup-token"],
            "user": {
                "email": config["email"],
                "password": config["password"],
                "first_name": "Wonderland",
                "last_name": "Local Admin",
            },
            "prefs": {
                "site_name": "Wonderland local analytics",
                "allow_tracking": False,
            },
        },
    )
session = request(
    "POST",
    "/api/session",
    json={"username": config["email"], "password": config["password"]},
)
client.headers["X-Metabase-Session"] = session["id"]
dbs = request("GET", "/api/database")["data"]
database = next((d for d in dbs if d["name"] == "Wonderland reporting"), None)
if not database:
    database = request(
        "POST",
        "/api/database",
        json={
            "name": "Wonderland reporting",
            "engine": "postgres",
            "details": {
                "host": args.database_host or url.host,
                "port": url.port,
                "dbname": url.database,
                "user": url.username,
                "password": url.password,
                "ssl": args.allow_cloud_reporting,
                "additional-options": "sslmode=verify-full&sslrootcert=/run/rds-ca/global-bundle.pem"
                if args.allow_cloud_reporting
                else "",
                "schema-filters-type": "inclusion",
                "schema-filters-patterns": "reporting",
            },
            "is_full_sync": True,
            "is_on_demand": False,
        },
    )
config["database_id"] = database["id"]
manifest = json.loads((ROOT / "analytics/dashboard.json").read_text())
dashboards = request("GET", "/api/dashboard")
dashboard = next((d for d in dashboards if d["name"] == manifest["name"]), None)
if not dashboard:
    dashboard = request(
        "POST",
        "/api/dashboard",
        json={"name": manifest["name"], "description": manifest["description"]},
    )
config["dashboard_id"] = dashboard["id"]
existing = request("GET", "/api/card")
cards = []
for index, spec in enumerate(manifest["cards"]):
    query = (ROOT / "analytics/queries" / spec["sql"]).read_text()
    body = {
        "name": spec["name"],
        "description": "Read-only SQL over persisted event facts. See repository analytics/queries.",
        "dataset_query": {
            "database": database["id"],
            "type": "native",
            "native": {"query": query, "template-tags": {}},
        },
        "display": spec["display"],
        "visualization_settings": {
            "graph.dimensions": [
                {
                    "daily-arrivals": "day",
                    "tickets-by-tier": "tier_name",
                    "revenue-by-tier": "tier_name",
                    "popular-attractions": "attraction_name",
                    "busy-quiet-hours": "hour",
                }.get(spec["key"], "day")
            ],
            "graph.metrics": [
                {
                    "daily-arrivals": "arriving_guests",
                    "tickets-by-tier": "purchased_tickets",
                    "revenue-by-tier": "revenue_cents",
                    "popular-attractions": "riders",
                    "busy-quiet-hours": "arriving_guests",
                }.get(spec["key"], "arriving_guests")
            ],
        },
    }
    card = next((c for c in existing if c["name"] == spec["name"]), None)
    card = (
        request("PUT", f"/api/card/{card['id']}", json=body)
        if card
        else request("POST", "/api/card", json=body)
    )
    result = request("POST", f"/api/card/{card['id']}/query", json={})
    if result.get("status") != "completed":
        raise SystemExit(f"Stored SQL verification failed for {spec['key']}")
    print(f"Verified stored SQL: {spec['key']} ({len(result['data']['rows'])} rows)")
    cards.append(
        {
            "id": -(index + 1),
            "card_id": card["id"],
            "row": (index // 2) * 5,
            "col": (index % 2) * 12,
            "size_x": 12,
            "size_y": 5,
            "parameter_mappings": [],
            "visualization_settings": {},
        }
    )
request(
    "PUT",
    f"/api/dashboard/{dashboard['id']}",
    json={
        "name": manifest["name"],
        "description": manifest["description"],
        "dashcards": cards,
    },
)
verified = request("GET", f"/api/dashboard/{dashboard['id']}")
if len(verified.get("dashcards", [])) != len(cards):
    raise SystemExit("Dashboard card count verification failed")
save()
request("DELETE", "/api/session", json={"session_id": session["id"]})
print(f"Private dashboard ready: {args.metabase_url}/dashboard/{dashboard['id']}")
print("Login credentials saved privately; never commit or share the credential file")
