# Wonderland MVP

A theme park booking demo with a separate visitor app and administrator app.

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
