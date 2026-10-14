# Phase 4 outcome — durable events and stored analytics

Phase 4 was authorized after Phase 3. Local implementation is complete for review. Stop before Phase 5 (Minikube). No AWS account connection, cloud resource, payment-provider request, Git commit or push was performed by this phase.

## Objectives and implementation

Booking confirmation, full-party arrival and ride recording retain their transactional outboxes. The analytics process polls both outboxes once per second, publishes into a durable PostgreSQL queue, then projects validated version-1 envelopes into its owned reporting schema. Outbox-to-local-queue delivery and the published marker commit in one transaction. Queue consumption locks one eligible row with `FOR UPDATE SKIP LOCKED`; facts, the event-ID/hash deduplication record and completion acknowledgment commit together. An interrupted transaction rolls back and can be retried. Several publishers/consumers can run concurrently.

Invalid messages roll back partial projection using a savepoint, retry with exponential delays (2 and 4 seconds before the third attempt), and enter a durable dead-letter state after three attempts. Database failures roll back the entire attempt and retry on the next polling cycle. A matching replay changes no totals; a reused event ID with different content fails. Administrator-only endpoints list dead-letter IDs/reasons and explicitly redrive a dead event. Redrive resets attempts; it does not repair malformed payloads. Fix the cause before redriving. Rows, completed messages and deduplication records are retained; retention/archival policy remains future work.

Local transport intentionally shares the PostgreSQL instance and transaction boundary with the outboxes. It demonstrates durable buffering and recovery, but is not an SQS emulator and cannot isolate a database outage. A dependency-injected SQS adapter implements send-before-outbox-ack and projection-commit-before-delete. Offline tests prove replay after a failed send transaction and lost delete acknowledgment. No AWS SDK session or account connection is created. Cloud wiring, IAM, queue visibility tuning, redrive policy and actual SQS delivery await approved later phases. Do not switch transports on an already-published dataset without an explicit replay/migration procedure.

## Files

- `services/analytics-worker/app/{main,pipeline,sqs_transport}.py`: worker, protected reports, retries, dedupe, dead-letter/redrive and offline SQS adapter.
- `services/analytics-worker/migrations/`: queue, dedupe, three fact tables, indexes and reporting views.
- `services/gate-ride-service/app/routes.py`: additive attraction-name snapshot in new ride events. Older events without the label remain compatible; labels fall back to the attraction ID until a named event arrives.
- `analytics/dashboard.json`, `analytics/queries/*.sql`: reproducible dashboard manifest and seven actual SQL questions.
- `frontend/src/AnalyticsPanel.tsx`, `AdminPanel.tsx`: protected Analytics tab with metrics, pending-event counts and processing status.
- `scripts/{db_migrate,local_phase3,local-postgres,run-local-services}.py`, Compose and Dockerfiles: configuration upgrade, reporting role, read-only BI role, migration and worker wiring. Existing keys/passwords/data are preserved.
- `scripts/{run-metabase,provision-metabase,smoke-phase4}.py`: local platform, repeatable provisioning and reconciliation.
- `tests/test_phase4.py`: real PostgreSQL pipeline/metrics/security tests; health fixtures now require the analytics DB too.

## Metric definitions

| Required metric | Stored query and meaning |
|---|---|
| Daily arrivals | Sum arriving party guest counts by the actual arrival instant converted to Asia/Colombo; booking count also available |
| Purchased tickets by tier | Count confirmed-purchase facts (one ticket/booking); booked guest sum is separate |
| Revenue by tier | Sum immutable confirmed purchase snapshot amounts in integer USD cents; frontend formats dollars |
| Most popular attractions | Rank by rider guest counts; ride-event counts also shown; stable attraction IDs prevent rename splits |
| Busiest/quietest hours | Sum arrivals per opening hour across the reporting period; every hour 09–17 is included even with zero arrivals; ties share ranks |

Opening hours 09:00 inclusive to 18:00 exclusive are a **provisional assumption**, not a course requirement. Daily zero-filled opening-hour rows run from the first arrival date through today (or the latest arrival date if later). With no arrivals, today's nine hours all have zero counts and share both ranks. Arrivals outside those hours remain in daily totals and a separate question; they are not silently dropped. The charts use all stored history; there is no dashboard date filter yet. Tier and attraction grouping uses stable IDs and the latest available event snapshot label, rather than querying operational tables. Admin API returns up to 366 daily rows; Metabase SQL queries have no such daily-row cap.

## Local commands

With the dependencies and frontend already installed:

```bash
.venv/bin/python scripts/local-postgres.py start
.venv/bin/python scripts/run-local-services.py
# Another terminal:
npm --prefix frontend run dev -- --host 127.0.0.1
# Another terminal, while APIs and Vite run:
.venv/bin/python scripts/smoke-phase3.py --scenario phase4-demo
.venv/bin/python scripts/smoke-phase4.py
```

The Phase 3 smoke script deliberately creates a labelled local simulator booking and uses its documented development-only date adjustment to exercise same-day arrivals. Different scenario names create separate demo records. Reporting queries include those local demo records; they are not production visitor statistics. No fabricated series is injected into charts.

Metabase OSS **v0.58.35**, the inspected 0.58 LTS release, runs on the installed Java 21. Its [versioned JAR instructions](https://github.com/metabase/metabase/blob/v0.58.35/docs/installation-and-operation/running-the-metabase-jar-file.md) specify Java 21. Download only the pinned official artifact:

```bash
mkdir -p tmp/metabase
curl -fL https://downloads.metabase.com/v0.58.35/metabase.jar -o tmp/metabase/metabase.jar
shasum -a 256 tmp/metabase/metabase.jar
.venv/bin/python scripts/run-metabase.py
# Another terminal, after http://localhost:3000/api/health responds successfully:
.venv/bin/python scripts/provision-metabase.py
```

Observed JAR SHA-256: `922f061ef009ccb131f06022a1b8a2d03ff64ddc5eb1b9880126924b4ab0005f`. This records the downloaded bytes; it is not a vendor signature. Files under `tmp/` and `secrets/` remain ignored. The native runner binds loopback and disables anonymous tracking/update checks. Its H2 application metadata is suitable only for local development; managed production metadata storage remains future work. Ctrl-C stops each foreground runner. The Metabase runner never replaces existing metadata.

Provisioning creates/reuses the named database, SQL questions and dashboard and verifies each question through Metabase's API. It does not create a public sharing link. Login details are in the private mode-0600 `secrets/metabase.json`; open that file locally, never paste it into a chat/report/commit. Metabase login is separate from the application's developer/Cognito identity. The private dashboard created here is [Wonderland stored event analytics](http://localhost:3000/dashboard/2). Its ID may differ in a fresh installation; use the provisioning output.

For Docker when available, regenerate `secrets/compose.env`, then run Compose with `--profile analytics`. Provision against that file with `--env-file secrets/compose.env --database-host postgres`. Native and Docker Metabase cannot both bind port 3000. A credential file belongs to the corresponding Metabase metadata instance; if changing instances, preserve the matching credentials/metadata together. Docker execution remains unverified on this machine.

`APP_ANALYTICS_ENABLED=false .venv/bin/python scripts/run-local-services.py` starts the reporting API without processing. Stop the existing project API runner first to free its ports. Create a new named smoke scenario; inspect unpublished count versus unchanged reporting facts. Stop the paused runner and restart normally; run `scripts/smoke-phase4.py` to verify catch-up. Do not truncate development data. Frontend development links to local Metabase; production builds show that link only when public `VITE_METABASE_URL` is configured.

## Acceptance evidence — 14 October 2026

- 96 automated tests passed, no skips; 10 Phase 4 tests cover queue rollback, dedupe/conflicting IDs, concurrent consumers, retries/DLQ/redrive authorization, timestamps/zero hours/ties/cents, source publication recovery, offline SQS replay, and reporting/BI privilege isolation. One existing upstream Starlette TestClient deprecation warning remains.
- TypeScript checking and Vite production build passed.
- Four native API readiness checks passed.
- With processing disabled, a real simulator purchase, four-guest arrival and two-rider event succeeded: three unpublished events remained; operational confirmed bookings increased from six to seven while purchase facts stayed at six.
- After normal restart: seven purchases / 98,000 cents / 28 booked guests; four arrivals / 16 guests; three ride events / six riders. Each reporting total matched its operational source; no pending/dead events remained. These are the observed local demo totals at verification time.
- All seven Metabase SQL questions executed successfully using the actual read-only reporting connection. Provisioning was rerun successfully without duplicate dashboards/questions. The first rerun exposed the API retaining a setup token after initialization; provisioning now checks `has-user-setup` before setup.
- Reporting role can acknowledge only the `published_at` column in operational outboxes, cannot read operational bookings, and cannot update migration records/facts. BI can select reporting views, cannot read the raw queue or operational bookings, and has a read-only transaction default.

## Remaining review and risks

Fresh interactive UI/chart-layout review remains pending after the prior browser security rejection; backend API contracts, stored SQL execution and frontend build were verified. No claim of screenshots or browser end-to-end coverage is made. Docker and remote CI were not run. Actual Cognito, Stripe test-account delivery and SQS remain unverified. Shared PostgreSQL is still a common failure domain. This phase does not implement Kubernetes, cloud monitoring alerts, archival, report date filters, refunds/revocation or production capacity testing. Review the local Analytics tab and Metabase dashboard before Phase 5.
