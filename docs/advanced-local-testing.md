# Complete local run and test guide

Use this guide before moving on to cloud deployment. Start with **Part A (native application)**, complete the manual checks, then use **Part B (local Kubernetes)** for deployment and failure demonstrations. All commands run from the repository root on this Mac.

This guide uses signed local identities and simulated payments. AWS credentials, Cognito accounts and Stripe accounts are unnecessary. Dependency/image downloads may need internet access. Do not run cloud deployment commands for these tests.

## 1. Choose the environment

| Environment | Visitor / administrator URLs | Database/configuration | Use |
|---|---|---|---|
| Native | http://localhost:5173 / http://localhost:5174 | Native PostgreSQL on 55432; `secrets/local.env` | Full browser walkthrough, tests and Metabase |
| Minikube | http://localhost:5180 / http://localhost:5181 | Separate cluster PostgreSQL/PVC; `secrets/kubernetes.env` | Containers, service discovery, recovery and HPA |
| Compose (optional alternative) | http://localhost:5173 / http://localhost:5174 | Separate Docker volume; `secrets/compose.env` | Alternate container startup; runtime not yet verified here |

Native and Minikube have separate records and signing keys. Their sign-in passwords and tokens are not interchangeable. Native Metabase reads the native database, so Kubernetes purchases do not appear there. Avoid running native and Compose together: both use ports 5173, 5174 and 8001–8004.

## Part A — Native application

### 2. Prerequisites and one-time dependency setup

Open Terminal and enter:

```bash
cd /Users/sadithaudayanga/Projects/wonderland
python3.12 --version
uv --version
node --version
npm --version
/opt/homebrew/opt/postgresql@17/bin/postgres --version
```

Required: Python 3.12, uv, Node.js 22.12 or newer, npm and PostgreSQL 17. These tools and the project environment have already been prepared on this Mac. Java 21 is also needed for optional Metabase. Docker is unnecessary for the native application; the validation script checks Compose configuration if its CLI is installed.

On a fresh checkout, create the virtual environment **only if `.venv` does not exist**, then install the locked dependencies:

```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
```

For an existing environment after dependency changes, run only the last two commands. No virtual-environment activation is required: commands below use its Python directly. On another Mac, install missing tools first; PostgreSQL can be installed with `brew install postgresql@17`.

Keep `frontend/.env` in local auth mode if you have created it (`VITE_AUTH_MODE=local`; see `.env.example`). Use the existing generated secrets; do not replace them with example values or delete them to restart.

### 3. Start the database and APIs — Terminal 1

```bash
cd /Users/sadithaudayanga/Projects/wonderland
.venv/bin/python scripts/local-postgres.py start
.venv/bin/python scripts/run-local-services.py
```

The first command starts the project database, applies migrations/seeds and creates missing private configuration. Repeating it preserves existing data, keys and administrator edits. The second command stays running and starts four services:

| Service | Local address |
|---|---|
| Attractions/catalog | http://127.0.0.1:8001 |
| Booking/payment/profile | http://127.0.0.1:8002 |
| Gate/ride history | http://127.0.0.1:8003 |
| Analytics/reporting worker | http://127.0.0.1:8004 |

Keep this terminal open. Start only one API runner. Database startup by itself does not start the APIs.

### 4. Start the frontend — Terminal 2

```bash
cd /Users/sadithaudayanga/Projects/wonderland
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open **http://localhost:5173/** for visitors. Start the separate administrator app in another terminal and keep it running:

```bash
cd /Users/sadithaudayanga/Projects/wonderland
npm --prefix frontend run dev:admin
```

Open **http://localhost:5174/** for administration. Both apps use the same native APIs/database but have separate entry points, builds and in-memory sessions. Vite uses strict ports: a conflict fails startup instead of silently changing the URL. The visitor app has no administrator navigation or dashboard.

### 5. Run the automated checks — Terminal 3

With the database, API runner and frontend running:

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./scripts/check-local.sh
.venv/bin/python scripts/smoke-local.py
.venv/bin/python scripts/smoke-phase2.py
.venv/bin/python scripts/smoke-phase3.py --scenario local-acceptance
.venv/bin/python scripts/smoke-phase4.py
```

Run each command in order and resolve any failure before proceeding.

| Command | What must succeed |
|---|---|
| `check-local.sh` | Python tests, production frontend build and Compose configuration validation when its CLI is available |
| `smoke-local.py` | All four services pass readiness checks |
| `smoke-phase2.py` | Real HTTP catalog → stored booking → simulated payment → confirmed signed ticket and owned booking history |
| `smoke-phase3.py` | Profile, administrator access, same-day signed ticket, full-party arrival, duplicate protection, ride usage and owned history |
| `smoke-phase4.py` | Persisted reporting totals reconcile with source purchases, revenue, arrivals and rides; report authorization and hourly structure pass |

The last recorded full Python run passed **131 tests with no skips**. That is historical evidence, not a claim that this guide has rerun them. Check your new output: database integration skips mean the full database suite did not execute. The native setup supplies a dedicated `wonderland_test` database; tests must never point at the development database. A configured but unavailable test database is a failure.

The HTTP smoke scripts deliberately add local demo records to the development database. The Phase 2 visitor is `demo-visitor`; Phase 3 uses `phase3-demo-visitor`. Same-day reruns with the same scenario reuse stable identifiers; a new scenario deliberately adds another purchase/visit. Analytics waits briefly for asynchronous processing, so immediate UI totals can lag.

### 6. Sign in as a visitor or administrator

Database setup generates private email/password accounts in `secrets/local.accounts.json` and stores only salted password hashes in the backend configuration. Open the credential file locally; do not share, screenshot or commit its passwords. There are no token-copy controls in either app.

| App / test identity | Email | Existing subject (for smoke data) |
|---|---|---|
| Visitor app on 5173 | `visitor@wonderland.local` | `demo-visitor` |
| Administrator app on 5174 | `admin@wonderland.local` | `demo-admin` |
| Manual gate-test visitor on 5173 | `gate-test@wonderland.local` | `phase3-demo-visitor` |
| Other visitor for ownership checks | `other@wonderland.local` | `another-visitor` |

Use the matching generated password from the private file. Select **Sign in** on the visitor app; the administrator app opens at its own sign-in page. Administrator credentials are rejected by the visitor portal, and visitor credentials are rejected by the administrator portal. The backend also checks roles for every protected operation.

Sessions stay in memory and expire after one hour; refreshing or signing out requires signing in again. Existing bookings remain. If you upgraded an already running app, rerun `scripts/local-postgres.py start` and restart the API runner once to load the new account hashes. The CLI token tool remains for scripted API tests, not browser login. No AWS account is needed.

### 7. Visitor walkthrough

Complete these checks in the visitor window:

| Check | Action | Expected result |
|---|---|---|
| Public catalog | Sign out, browse/search attractions and open details | Catalog works without login; status and suitability information appear |
| Protected booking | Try booking while signed out | Authentication is required |
| Profile | Sign in as visitor, edit display name/language, save and reopen | Saved profile is returned for that identity |
| Booking | Select an active tier, allowed guest count, tomorrow and a listed time slot | Pending booking has a reference and the server's stored total |
| Validation | Try an out-of-range party size or past date | Form/API rejects invalid input; no valid purchase is created |
| Payment | Start test checkout, then select **Simulate successful test payment** | Booking becomes confirmed; no real card or payment account is used |
| Ticket | Open the confirmed ticket | Signed QR ticket and visit/party details appear |
| History | Open My bookings | Your new booking and its stored price appear |
| Ownership | Sign out; sign in as `other@wonderland.local` | Other visitor cannot see the first visitor's bookings/history |
| Session | Refresh the page | Sign-in is required; saved bookings remain in the database |

A booking left before successful payment stays pending and must not receive a confirmed ticket. Normal bookings are limited to today through 365 days ahead; elapsed same-day slots are rejected. Use tomorrow for the ordinary booking walkthrough. Refunds, cancellation, re-entry and partial-party admission are outside the implemented scope.

### 8. Prepare an unscanned ticket for today's manual gate test

Tomorrow's normal ticket cannot be admitted today. Also, the full Phase 3 smoke test has already checked in its own ticket. Prepare a **different** scenario that stops before admission:

```bash
.venv/bin/python scripts/smoke-phase3.py --scenario manual-gate --prepare-only
```

Sign in at port 5173 as `gate-test@wonderland.local` using its private password, open My bookings and select the prepared booking reference printed by the script. Open its ticket and copy **Ticket scan content**. Record the reference privately for the ride test.

The preparation script uses a documented local-only database fixture to set today's visit date before normal simulated payment. This allows a gate demonstration even after today's booking slots have passed. It is test-data preparation, not a normal visitor booking flow. If `manual-gate` has already been admitted today, choose a fresh scenario such as `manual-gate-2`.

In the separate administrator app on port 5174:

1. Open **Gate check-in** and paste the signed ticket content into **Scanned QR ticket content**.
2. Select **Validate ticket**. Expect the correct reference, today's date and **4 guests**, ready for check-in.
3. Try an arriving count smaller than 4. Expect rejection because the full party must arrive together.
4. Restore 4 and register arrival. Expect one successful arrival.
5. Validate the same ticket again. Expect **Already checked in** and admission disabled. The API also rejects duplicate admission (409); the automated scenario verifies this.
6. Try a tomorrow ticket or altered signed content. Expect rejection; no additional arrival should be stored.

Treat ticket content as private too. Do not publish a readable QR or signed scan payload in evidence.

### 9. Ride usage and visitor history

Using the admitted booking reference:

1. Open administrator **Ride usage**, choose an open attraction and record 2 riders.
2. Expect a success message and the ride in today's operational totals.
3. Return to the `gate-test@wonderland.local` visitor window and open visit history. Expect the arrival and ride associated with this booking.
4. Try a booking with no arrival today, or riders exceeding its booked party. Expect rejection.
5. A maintenance/retired attraction must not accept ride usage. The UI may filter it out; automated API tests cover rejection.

Separate new submissions may represent separate rides. Duplicate protection is based on the same event identifier; the smoke/integration tests verify retries do not count twice. Do not assume clicking a new submission is an idempotent retry.

### 10. Administrator catalog, pricing and analytics

Use temporary test records for editing; leave the seeded Family tier and open attractions intact until the smoke tests finish.

| Area | Manual check | Expected result |
|---|---|---|
| Attractions | Create a clearly labelled test attraction, edit its details/status, then retire it | Saved changes appear; retired/maintenance rides cannot be recorded as open rides |
| Pricing | Create/edit a temporary tier with valid guest bounds and a price; deactivate it afterward | Booking choices use active stored tiers and enforce their bounds |
| Price snapshot | If testing an existing tier price, record its original value, purchase before/after the edit, then restore the original value | Existing bookings retain their original total; new bookings use the new price |
| Overview | Inspect sales, arrivals and ride totals | Totals reflect stored local activity |
| Analytics | Open Analytics and refresh after processing | Purchases, revenue, daily arrivals, popular rides and hourly arrivals are present; queue eventually drains |
| Authorization | Attempt sign-in with visitor credentials in the administrator app | Protected administrator/reporting APIs deny access; hiding navigation alone is not the security check |

Revenue is stored in integer USD cents. Daily/hourly grouping uses **Asia/Colombo**. Hourly reporting currently uses the provisional operating window **09:00–18:00**, with buckets starting 09:00 through 17:00. An arrival created at night still increases daily arrivals but appears in outside-hours reporting; all operating-hour buckets can correctly remain zero. Tied busiest/quietest hours can share ranks.

### 11. Metabase dashboard — optional Terminal 4

Keep the native database and APIs running. Check Java:

```bash
java -version
```

Use Java 21. On this Mac the pinned JAR has already been prepared. If `tmp/metabase/metabase.jar` is absent, obtain the pinned artifact:

```bash
mkdir -p tmp/metabase
curl -fL https://downloads.metabase.com/v0.58.35/metabase.jar -o tmp/metabase/metabase.jar
shasum -a 256 tmp/metabase/metabase.jar
```

Previously recorded SHA-256: `922f061ef009ccb131f06022a1b8a2d03ff64ddc5eb1b9880126924b4ab0005f`. This is a recorded artifact hash, not a vendor signature. See [Phase 4 outcome](phase-4-outcome.md) for the pinned version details.

Start Metabase in Terminal 4:

```bash
.venv/bin/python scripts/run-metabase.py
```

After startup, in Terminal 3:

```bash
curl -fsS http://127.0.0.1:3000/api/health
.venv/bin/python scripts/provision-metabase.py
```

Wait for health success before provisioning; Java startup can take time. Provisioning creates/reuses the private dashboard and verifies its saved queries. Open **http://localhost:3000/** and sign in using the private `secrets/metabase.json` file, opened locally. Metabase has its own login; application visitor/admin accounts do not log into it. Use the dashboard URL printed by provisioning; an existing instance used `/dashboard/2`, but fresh IDs can differ.

Verify the seven saved questions load, the five required metrics agree with native Analytics, and zero/empty results are explained by actual data/date filters. This local instance uses development-only H2 metadata and a restricted BI database role. Preserve its metadata and credential file together.

### 12. Native worker recovery demonstration — optional

This briefly pauses analytics processing while leaving the domain services available:

1. Stop Terminal 1's API runner with Ctrl-C; leave PostgreSQL and Vite running.
2. Restart the APIs with processing disabled:

   ```bash
   APP_ANALYTICS_ENABLED=false .venv/bin/python scripts/run-local-services.py
   ```

3. In Terminal 3, create a fresh full scenario:

   ```bash
   .venv/bin/python scripts/smoke-phase3.py --scenario native-recovery
   ```

4. Expect booking, payment, arrival and ride operations to succeed. Analytics facts should lag and unpublished work should accumulate. Do not run Phase 4 reconciliation expecting success while processing is paused.
5. Stop the paused runner; restart normally in Terminal 1:

   ```bash
   .venv/bin/python scripts/run-local-services.py
   ```

6. Run `.venv/bin/python scripts/smoke-phase4.py`. Expect catch-up and reconciliation without double-counting. Choose a new scenario name if reusing this demonstration later on the same day.

## Part B — Local Kubernetes

### 13. Start the isolated cluster and deploy

This Mac's prepared setup uses Colima profile `wonderland` and Minikube profile `wonderland`. Allow enough memory/disk; the Colima VM uses 4 CPUs, 6 GiB RAM and a 30 GiB disk. Initial images/builds can take several minutes. See [local Kubernetes guide](local-kubernetes.md) for first-machine installation/plugin setup.

In a terminal at the repository root:

```bash
colima start --profile wonderland --cpu 4 --memory 6 --disk 30 --runtime docker --vm-type vz
.venv/bin/python scripts/local-kubernetes.py start
.venv/bin/python scripts/local-kubernetes.py build
.venv/bin/python scripts/local-kubernetes.py deploy
.venv/bin/python scripts/local-kubernetes.py verify
.venv/bin/python scripts/local-kubernetes.py forward
```

Each command has a separate purpose: start creates/resumes Minikube and enables metrics-server; build builds the local images; deploy applies database/migrations/workloads; verify checks readiness; forward stays running and exposes the gateway. Do not omit build/deploy on a fresh cluster. On an unchanged existing deployment you can resume with start, verify and forward; if verify fails, inspect the failure and rebuild/deploy as needed.

Open **http://localhost:5180/** for visitors and **http://localhost:5181/** for administration. The same port-forward command exposes both. The helpers use a private dedicated kubeconfig and validate the named local cluster; avoid ad hoc commands against an unspecified kubectl context.

### 14. Test the Kubernetes business flow

Keep port-forward running. In another terminal:

```bash
.venv/bin/python scripts/smoke-kubernetes.py --scenario local-acceptance
```

Open private `secrets/kubernetes.accounts.json` locally. Sign in at port 5180 with `kube-test@wonderland.local` to inspect the smoke visitor (`phase5-demo-visitor`), or `visitor@wonderland.local` for a new visitor flow. Sign in at port 5181 with `admin@wonderland.local`. Use the matching cluster passwords, not native passwords. Expect the smoke script to complete simulated purchase, signed ticket, arrival, ride and reporting reconciliation.

Repeat the browser checks from Part A using the cluster accounts. Rebuild and redeploy existing clusters to install the separate app and local login configuration. Native `smoke-phase2.py`, `smoke-phase3.py` and `smoke-phase4.py` target the native environment; use `smoke-kubernetes.py` for cluster integration. Native Metabase remains connected to native data.

### 15. Run recovery, deployment and scaling tests sequentially

Keep forwarding active and run **one command at a time**, waiting for its restoration checks to finish:

```bash
.venv/bin/python scripts/demo-kubernetes.py self-heal
.venv/bin/python scripts/demo-kubernetes.py blue-green
.venv/bin/python scripts/demo-kubernetes.py recovery
.venv/bin/python scripts/demo-kubernetes.py readiness
.venv/bin/python scripts/demo-kubernetes.py autoscale
.venv/bin/python scripts/local-kubernetes.py verify
.venv/bin/python scripts/smoke-kubernetes.py --scenario post-recovery
```

| Demonstration | Expected observation |
|---|---|
| Self-heal | A catalog pod is deleted; another replica serves requests; a replacement pod with a new UID becomes ready |
| Blue-green | Separate green deployment becomes ready; stable service switches to version metadata 0.5.1, then restores blue 0.5.0 and green scales to zero |
| Recovery | Worker is scaled to zero; business operations succeed and outbox work persists; restored worker catches up without duplicates |
| Readiness | PostgreSQL is temporarily stopped; API liveness stays healthy but readiness fails and endpoints are removed; database restoration preserves records |
| Autoscale | Real concurrent catalog traffic drives the HPA from 2 to 3 ready replicas; it returns to 2 after load ends |
| Final verification | All workloads are ready again and a fresh complete smoke scenario succeeds |

The green image uses the same domain artifact with distinct version metadata: this demonstrates switching and rollback, not a new business feature. Autoscaling sends 16 concurrent clients for 100 seconds and waits for controller sampling/scale-down; allow several minutes. Exact throughput depends on your Mac; the prior run's request count is not a pass threshold. If a demo fails or is interrupted, run verify and inspect the failure before continuing; deploy reapplies the intended baseline, followed by verify. Do not redeploy during an active demo.

## 16. Optional Compose alternative

Compose configuration is validated, but its complete runtime has not been exercised here. Use native plus Minikube as the established verification paths. If you want to test Compose too, stop native APIs/Vite and native Metabase first to free their ports:

```bash
.venv/bin/python scripts/configure-compose.py
docker compose --env-file secrets/compose.env config --quiet
docker compose --env-file secrets/compose.env up --build -d --wait
.venv/bin/python scripts/smoke-local.py
```

Use credentials from private `secrets/compose.accounts.json` at visitor port 5173 and admin port 5174. The native domain smoke scripts use native credentials/database and are not Compose acceptance scripts. For optional Compose Metabase setup and its distinct credential/metadata instance, follow [development guide](development.md). Always include `--env-file secrets/compose.env`; never collect expanded `docker compose config` without `--quiet` because it exposes credentials.

## 17. Stop safely and resume later

For native mode:

1. Ctrl-C both visitor and administrator frontend terminals.
2. Ctrl-C the API runner terminal.
3. Ctrl-C Metabase if running.
4. Stop the project database:

   ```bash
   .venv/bin/python scripts/local-postgres.py stop
   ```

For Kubernetes, Ctrl-C port-forward, then:

```bash
.venv/bin/python scripts/local-kubernetes.py stop
colima stop --profile wonderland
```

For Compose:

```bash
docker compose --env-file secrets/compose.env down
```

These stops preserve data. Do not delete `secrets/`, `tmp/postgres`, Metabase metadata, Kubernetes PVCs or Docker volumes to perform a routine restart. Regenerating signing keys invalidates existing tokens/tickets; changing configuration passwords alone does not update existing database passwords. Resume using the startup steps for your selected environment and sign in again.

## 18. Troubleshooting

| Symptom | Check / recovery |
|---|---|
| Connection refused / smoke fails immediately | Start PostgreSQL, then APIs, then Vite; confirm the appropriate frontend port |
| Address already in use | Inspect `lsof -nP -iTCP:5173 -sTCP:LISTEN` (substitute the failing port); stop the known duplicate runner in its own terminal |
| Python module missing | Sync `requirements-dev.lock` into `.venv`; use `.venv/bin/python` |
| Test database unavailable or integration skipped | Run native database start; use its generated local configuration and dedicated test database; do not substitute the development URL |
| 401 after refresh or an hour | Sign in again; check that credentials match native versus Kubernetes configuration |
| 403 administrator endpoint | Use the administrator app and its administrator account; visitor denial is expected |
| Gate rejects ticket | Confirm today's Colombo date, confirmed payment, matching environment, unchanged signed payload and no previous arrival |
| Manual gate says already admitted | Prepare a fresh `--scenario ... --prepare-only` ticket and use its printed reference |
| Ride rejected | Require today's arrival, an open attraction and rider count no greater than booked party size |
| Analytics lag / Phase 4 timeout | Ensure worker processing is enabled and healthy; restart the normal API runner after a pause; inspect backlog before retrying |
| Daily arrival exists but hourly chart is zero | Check whether admission happened outside the provisional 09:00–18:00 Colombo window |
| Metabase not ready | Keep its terminal open; check Java 21, free port 3000 and wait for `/api/health` success |
| Metabase login/data appears wrong | Use the matching private credentials/metadata instance; native dashboards do not read Kubernetes records |
| Kubernetes Docker/build failure | Start the named Colima profile; check local Docker/Buildx plugin setup in the Kubernetes guide |
| HPA does not grow | Verify metrics-server/cluster readiness and CPU requests; allow controller delay and sufficient host resources; record a failed demonstration rather than claiming scaling |

Do not paste private environment files, database URLs, token output, ticket payloads or expanded secret manifests into troubleshooting evidence.

## 19. Acceptance record and evidence

Record your actual run date, environment, Git revision (`git rev-parse --short HEAD`), command results and any unresolved failures. Screenshots should hide tokens, QR payloads and credentials. Useful evidence: catalog, confirmed booking, ticket details with QR obscured, successful gate arrival, duplicate rejection, ride history, analytics and Metabase; capture Kubernetes script output for recovery and HPA.

| Acceptance item | Native result / notes | Kubernetes result / notes |
|---|---|---|
| Automated tests/build, no unexplained skips | | Native test suite applies |
| Service readiness | | |
| Booking/payment/ticket/history | | |
| Visitor ownership and admin denial | | |
| Profile and administrator edits | | |
| Today's arrival and duplicate protection | | |
| Ride recording and history | | |
| Source/report reconciliation | | |
| Metabase saved questions/dashboard | | Separate native dashboard |
| Worker recovery | | |
| Pod self-heal and blue-green rollback | Not applicable | |
| Database readiness/recovery and persistence | | |
| HPA scale-up and scale-down | Not applicable | |
| Safe stop/resume | | |

Local acceptance is complete when the required commands pass, the manual flows match their expected results, failure demonstrations restore healthy service, and all exceptions are recorded. Actual AWS, Cognito, SQS and external Stripe delivery remain separate cloud/account verification work; local success does not establish those integrations.
