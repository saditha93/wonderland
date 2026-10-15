# Wonderland MVP

A theme park booking demo with a separate visitor app and administrator app.

For the selected no-domain AWS deployment, use the [small AWS demonstration guide](docs/simple-aws-demo.md). Cloud source and offline checks are prepared; live deployment is pending IAM permission approval.

## Run

On this Mac, the dependencies are already installed. Open one terminal:

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./start.sh
```

Keep the terminal open. It starts the database, APIs and both apps, then shows your private sign-in details.

- **Visitor:** http://localhost:5173 — browse, book, pay and view tickets.
- **Admin:** http://localhost:5174 — manage attractions/prices, check in visitors, record rides and view reports.

Press **Ctrl-C** to stop the apps. Bookings and passwords stay saved. Run the same command next time.

## Demonstrate

Follow the [short demo guide](docs/demo-guide.md). The main flow is:

**Book today's visit → demo payment → ticket → admin check-in → ride → reports.**

The local launcher allows today's bookings even after the chosen slot, so you can rehearse at any time. Payments are simulated; no money is charged. Existing booking data is preserved. No Docker, Kubernetes, Metabase or AWS setup is needed for this MVP walkthrough.

## Test

```bash
./start.sh test
```

This runs the Python tests and builds both apps. It does not create demo bookings or contact AWS.

## Assignment monitoring dashboard

Keep the app running, then open a second terminal:

```bash
./start.sh monitoring
```

This starts Metabase, verifies its seven saved queries and prints the dashboard URL/private login. See the [short assignment dashboard guide](docs/metabase-demo.md).

## Local infrastructure and handover

```bash
./start.sh infra-test   # Build/deploy locally and run recovery/scaling tests
./start.sh infra        # Open the Kubernetes visitor/admin apps
./start.sh infra-stop   # Stop the cluster/VM; keep data
./start.sh package      # Create the clean source ZIP
```

Run infrastructure commands one at a time. `infra-test` starts its own gateway; close an existing `infra` terminal first. See the [short infrastructure guide](docs/infrastructure-demo.md).

The [project report](docs/project-report.md) and [viva speaking guide](docs/viva-demo.md) are ready for your review. Local tests do not complete the original AWS deployment phase or verify remote GitHub CI.

## One-time setup on a fresh checkout

Use Python 3.12, uv, Node.js 22.12+ and PostgreSQL 17. On this Mac PostgreSQL binaries are under `/opt/homebrew/opt/postgresql@17/bin`.

```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
./start.sh
```

Create `.venv` only if it does not exist. Private accounts are generated under `secrets/`; do not share or commit them.

## Optional assignment material

The AWS, Kubernetes, Metabase, architecture and phase evidence files are retained separately for the SE6020 assignment. They are optional for this local demo. See [advanced documentation](docs/README.md). Actual cloud hosting/authentication and external payment delivery still require separate verification.
