# Local development and verification — Phase 3
Use Python 3.12 and Node.js 22.12+ (Node 22 is the container/CI baseline). Install Python dependencies from requirements-dev.lock and frontend dependencies with npm ci. Application verification used CPython 3.12 and available Node 26; Node 22 containers still require execution. Base images use tags, not digests; harden and verify architecture support before deployment.

## Native PostgreSQL on this Mac
Homebrew PostgreSQL 17.11 was installed for local verification. Homebrew also installed/upgraded its dependencies and created its default cluster; that default cluster was not started. We use a separate project cluster in ignored `tmp/postgres` on 127.0.0.1:55432 with SCRAM password authentication. No launch-at-login service was enabled.

```bash
# On another Mac only, if PostgreSQL binaries are missing:
brew install postgresql@17
# From this repository root:
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
.venv/bin/python scripts/local-postgres.py start
.venv/bin/python scripts/run-local-services.py
```

In another terminal: `npm --prefix frontend run dev -- --host 127.0.0.1`. Visit http://localhost:5173. Start only one copy of each server. Ctrl-C stops the four API children; stop Vite separately. Stop the project database with `.venv/bin/python scripts/local-postgres.py stop`. Database data and keys remain for the next start; stopping is not deletion.

The start script creates separate `wonderland` and `wonderland_test` databases, versioned schemas, four ticket tiers, six attractions, profiles/visits schemas and separate service roles. It preserves existing configuration and never overwrites administrator price/catalog edits when seeding. The native owner is a local-only migration superuser; APIs receive separate restricted database roles. Only booking receives payment secrets and the private RSA signing key. Gate receives the public key plus the opaque ownership-tag key. Do not copy this local owner setup into AWS.

Secrets are generated into ignored `secrets/local.env` and `secrets/native-postgres.password` with mode 0600. Do not delete/regenerate keys casually: access tokens and signed tickets depend on them. Database-role passwords are not automatically rotated; deleting configuration without resetting the disposable cluster can cause credential mismatch.

## Local identity and managed authentication boundary
Protected endpoints fail closed unless local mode is explicitly configured. There is no public token-minting HTTP endpoint or fake visitor registration. The developer CLI issues signed one-hour HS256 access tokens. Local identities are forbidden outside `local`/`test` environments; Cognito verification and frontend integration are implemented; actual AWS verification requires separate approval (see cognito-integration.md).

```bash
# These deliberately display a local credential in your private terminal:
.venv/bin/python scripts/local-token.py
.venv/bin/python scripts/local-token.py --subject another-visitor
# Admin API testing only; administrator UI is Phase 3:
.venv/bin/python scripts/local-token.py --subject demo-admin --role admin
# To avoid displaying a token, write it into an ignored file instead:
.venv/bin/python scripts/local-token.py --output tmp/visitor-token
```

Paste the visitor token into **Local development identity** at the bottom of the page and select Connect token. The browser verifies it through `/identity`, keeps it only in memory and clears it on refresh/disconnect. Never paste AWS credentials or payment keys. After refresh (including a Stripe redirect), reconnect a local token to view your own booking.

## Local booking demonstration
1. Browse attractions and details; note status and age/height guidance.
2. Connect a visitor token. Choose a tier, guest count, future date and time slot.
3. Submit once; the server stores the current price snapshot and a pending booking. Repeated identical commands with the same idempotency key reuse that booking.
4. Review the stored total. Start test checkout, then choose **Simulate successful test payment**.
5. The local simulator signs a server-generated event. Verification checks signature, freshness, checkout, amount and currency before confirming atomically and writing one outbox purchase event.
6. View/download the signed QR ticket and find the confirmed booking in My bookings. Returning without paying leaves it pending.

The local simulator does not contact Stripe or move money. Gate scanning, visit history, profiles and administrator management are implemented in Phase 3. Refund/cancellation policy, checkout-expiry recovery, capacity limits, reporting projections and queues are not implemented. Default booking date is tomorrow in Asia/Colombo; dates are limited to today through 365 days ahead and past same-day slots are rejected. Initial slots 09:00, 12:00 and 15:00 and Family/Group minimum of one guest are explicit provisional choices.

## Validation
```bash
./scripts/check-local.sh
# While APIs and Vite run:
.venv/bin/python scripts/smoke-local.py
.venv/bin/python scripts/smoke-phase2.py
.venv/bin/python scripts/smoke-phase3.py
```

PostgreSQL integration fixtures truncate only dedicated database names ending in `_test`; never point TEST_DATABASE_URL at valuable data. When TEST_DATABASE_URL is absent, those tests are skipped, not passed. Native setup creates it in private local.env, and CI provisions its own disposable PostgreSQL. A configured but unavailable test database fails the run. Health readiness checks catalog DB/schema revision and booking DB/schema revision plus signing/ownership keys; gate readiness verifies its SQL revision and public/ownership keys; analytics readiness remains skeleton-only.

The HTTP demo uses `demo-visitor` and creates a real stored, local simulated Family purchase for tomorrow. It reuses matching commands, so it can leave repeatable data you can inspect with the default visitor token. Automated tests use the separate test database and do not erase your development bookings.

## Docker Compose (prepared, not executed here)
Install/start Docker Desktop or equivalent Docker engine/Compose plugin manually. Stop native API/Vite processes before using their ports in Compose.

```bash
.venv/bin/python scripts/configure-compose.py
docker compose --env-file secrets/compose.env config --quiet
docker compose --env-file secrets/compose.env up --build -d --wait
.venv/bin/python scripts/smoke-local.py
.venv/bin/python scripts/local-token.py --env-file secrets/compose.env
```

Compose uses a separate generated secret file; its tokens are not interchangeable with native-mode tokens. It exposes PostgreSQL on loopback port 5433, services on 8001–8004 and frontend on 5173. Internal PostgreSQL hostname is `postgres:5432`. PostgreSQL becomes healthy, a one-shot migrator applies schemas/seeds/role grants, then catalog/booking start. Gate is database-backed and uses only its public ticket key. Analytics is still a skeleton. Always include the same --env-file on subsequent Compose commands. Never print `docker compose config` without --quiet when collecting public evidence: resolved configuration contains credentials.

Stop with `docker compose --env-file secrets/compose.env down`; named volumes persist. `down --volumes` intentionally deletes local database/Metabase volumes; use only for a deliberate disposable reset. Changing environment passwords does not change existing database passwords.

Optional Metabase: `docker compose --env-file secrets/compose.env --profile analytics up -d`. Configure manually at http://localhost:3000. Its embedded H2 metadata volume is development-only; real read-only reporting role, stored analytics facts and dashboards are Phase 4. Do not give Metabase the migration owner credential. This phase does not claim working dashboards.

## Optional Stripe test-account verification (manual, not performed)
The adapter creates test Checkout Sessions using backend snapshots and a stable provider idempotency key. Network calls use a five-second HTTP timeout and one SDK retry; a per-process circuit breaker opens after three failures, waits 30 seconds and permits a half-open probe. Booking remains pending on provider failure. The endpoint verifies the raw signed payload and never trusts the return URL to confirm payment.

To verify later, privately configure APP_PAYMENT_PROVIDER=stripe, APP_STRIPE_SECRET_KEY with your own sk_test_ key and APP_STRIPE_WEBHOOK_SECRET with the corresponding whsec_ secret in secrets/local.env; never share those values. Restart native APIs. If using the Stripe CLI, authenticate to your test account yourself and forward checkout.session.completed and checkout.session.async_payment_succeeded snapshot events to http://localhost:8002/payments/webhook. Use only Stripe's documented test payment details. No real keys or livemode events are accepted. Production-card payments are outside scope.

This integration has SDK/request/signature tests without network calls. No Stripe account was contacted; actual checkout/webhook delivery must be demonstrated before claiming external payment integration complete. Provider checkout expiry/replacement, refunds and revocation policy remain open before production readiness.

References: [Stripe webhook signature verification](https://docs.stripe.com/events/manage-webhook-endpoints#signature-errors), [Stripe Python SDK](https://github.com/stripe/stripe-python), [SQLAlchemy connections/transactions](https://docs.sqlalchemy.org/en/20/core/connections.html), [PyJWT validation](https://pyjwt.readthedocs.io/en/stable/usage.html).

## CI and cloud boundary
The workflow provisions disposable PostgreSQL for integration tests, builds the frontend, audits npm dependencies, prepares private Compose configuration, builds images and starts/migrates/checks containers. It has not run remotely. AWS deployments, Cognito, OIDC/protected environments and Terraform remain future phases requiring the user's explicit cloud approval.

## Phase 3 operation notes
Run scripts/local-postgres.py start again to apply migration 002 and visits migration 001, preserve existing keys, generate new RSA/ownership keys and grant the visits role. Do not start multiple API runners. The runner now leaves healthy siblings running when one exits, which supports fault demonstrations; Ctrl-C still stops all children it owns. Restore a stopped API by restarting the runner.

Local access tokens still expire after one hour. Use --subject demo-admin --role admin for administrator screens and --subject phase3-demo-visitor for the seeded visit history. Never self-assign administrator groups through profile/signup. In approved Cognito mode, sign-in happens through the SDK, tokens remain in memory and API calls fetch refreshed access tokens as needed.

Signed tickets now use RS256 with public-only gate verification. Re-open older confirmed tickets to generate the current format; legacy Phase 2 QR payloads are rejected. Gate checks the visit date and full party size, independent of booking API uptime. No partial arrivals, re-entry or refunds/revocation are supported. Ride recording checks today's arrival, party size and the live open catalog, propagates request IDs, and fails closed if catalog verification fails.

For manual gate testing after arrival slots have passed, `scripts/smoke-phase3.py --scenario manual --prepare-only` explicitly seeds a current-day visit date before normal verified local payment confirmation, then stops before scanning. This is a local test-data operation using the migration owner; it is not an exposed booking bypass or a normal visitor workflow. The demo identity is phase3-demo-visitor. Copy the ticket's Local demo gate scan data, switch to demo-admin, validate and register arrival. A second scan must return a duplicate error.

Arrival/ride timestamps are PostgreSQL timestamptz instants; daily operational totals convert to Asia/Colombo. Prices use integer cents. Booking and ride history preserve snapshots, while operational totals aggregate by stable IDs. Outbox publishing/reporting remain Phase 4.
