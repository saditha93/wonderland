# Implementation roadmap

User reviewed earlier phases and authorized Phase 6. Terraform/lifecycle implementation is validated offline and ready for review; stop before Phase 7 account access/deployment. Actual Cognito account verification remains pending. Actual Stripe test-account delivery remains unverified. Local application images now build/run in Minikube; remote CI and separate Compose runtime remain unverified. Later commands involving not-yet-created files are plans, not runnable instructions.

## Phase 0 — Read sources, trace requirements, agree design
- Files: `docs/*.md`.
- Steps: Extract PDFs; map p1–4 and rubric; select SQL; record risks.
- Commands: Read docs/requirements-matrix.md and docs/architecture-decisions.md.
- Acceptance: All mandatory scope mapped; conflicts visible.
- Tests: Inventory/page reference audit.
- Evidence: Private extraction inventory, public source index.
- Remaining risks: Deadline/IaC ambiguities; diagram review.

## Phase 1 — Minimal local foundation only
- Files: `services/*, frontend/, docker-compose.yml, tests/, .github/`.
- Steps: Create four health-only APIs, React shell, local Postgres/Metabase config.
- Commands: ./scripts/check-local.sh; see docs/development.md for the current Compose configuration.
- Acceptance: API tests and frontend build pass; Docker smoke pending if unavailable.
- Tests: pytest, TypeScript/build; optional Compose smoke.
- Evidence: Record real outputs in docs/validation.md.
- Remaining risks: No business/auth/payment/pipeline functionality.

## Phase 2 — Catalog, stored tiers, booking and test-payment domain
- Files: `services/attractions-service/, services/booking-service/, frontend/`.
- Steps: Migrations/seeds; integer cents; validation; idempotency; signed webhooks; QR/history.
- Commands: scripts/local-postgres.py start; scripts/db_migrate.py --seed; scripts/run-local-services.py; scripts/smoke-phase2.py (run with .venv/bin/python).
- Acceptance: Server pricing and exactly one confirmed purchase per valid payment.
- Tests: Domain, concurrency and webhook tests.
- Evidence: Booking/payment/ticket demo.
- Remaining risks: Requires reviewer acceptance of Phase 0/1; auth boundary must fail closed until P3.

## Phase 3 — Cognito/authorization, admin, gate and rides
- Files: `services/*/app/, frontend/`.
- Steps: JWT/ownership/admin; check-in constraints; ride and visit events.
- Commands: Local tests; AWS integration only when separately approved.
- Acceptance: Visitors denied admin; own history only; guest counts correct.
- Tests: JWT, authorization, ticket replay tests.
- Evidence: Denied requests and checked-in family.
- Remaining risks: No automatic AWS connection; partial-arrival/refund policy.

## Phase 4 — Durable event pipeline and actual dashboards
- Files: `services/analytics-worker/, analytics/`.
- Steps: Outbox; local transport adapter; SQS adapter; event dedupe; read model; dashboard provisioning.
- Commands: scripts/local-postgres.py start; scripts/run-local-services.py; scripts/run-metabase.py; scripts/provision-metabase.py; scripts/smoke-phase4.py (all with .venv/bin/python).
- Acceptance: Five mandatory metrics query persisted facts.
- Tests: Replay/crash/reconciliation/timezone tests.
- Evidence: Disabled-consumer backlog and restart reconciliation passed; seven Metabase SQL questions executed. See docs/phase-4-outcome.md.
- Remaining risks: Actual SQS/cloud integration and interactive chart review pending; provisional opening hours; shared database failure domain and retention.

## Phase 5 — Minikube and failure/scale demonstrations
- Files: `infrastructure/kubernetes/{base,local}, tests/`.
- Steps: Namespace/config/secret/probes/resources; Services; HPA; blue-green.
- Commands: scripts/local-kubernetes.py start/build/deploy/verify/forward; scripts/smoke-kubernetes.py; scripts/demo-kubernetes.py (all with .venv/bin/python).
- Acceptance: Discovery, scale, self-heal and rollback demonstrable.
- Tests: Fault injection/load; readiness failure and recovery.
- Evidence: Real pod replacement, live business/analytics flow, worker/DB recovery, blue-green switch/rollback and actual CPU HPA 2→3→2 verified; see docs/phase-5-outcome.md.
- Remaining risks: Single-node/shared-DB failure domain; provisional local resources; cloud gateway/security remain later work.

## Phase 6 — Real Terraform and lifecycle scripts
- Files: `infrastructure/terraform/, infrastructure/kubernetes/aws/, scripts/`.
- Steps: Pinned providers/modules, secure states, least privilege, stage core/edge/workloads; guard apply/destroy.
- Commands: scripts/validate-cloud.py (with .venv/bin/python); guarded cloud.py/preflight/deploy/verify/destroy commands only after account/action approval.
- Acceptance: Real scripts show target/plan/cost, refuse unapproved apply/destroy; no fake success.
- Tests: Static validation and script failure-path checks.
- Evidence: Four provider-valid mocked plans, local cloud manifest/TLS/Helm checks, refusal tests and actual lifecycle code; live plans remain Phase 7.
- Remaining risks: Real account/region/domain/versions/prices/permissions and all managed integration/cleanup remain unverified. See docs/phase-6-outcome.md.

## Phase 7 — Approved cloud rehearsal
- Files: `AWS resources and evidence docs`.
- Steps: Ask explicit approval after plan; provision, build/push, deploy/migrate/seed, verify, approved cleanup.
- Commands: scripts/preflight.sh; scripts/deploy-demo.sh; scripts/verify-demo.sh; scripts/destroy-demo.sh (created P6).
- Acceptance: Cloud Cognito, EKS, Gateway, Amplify and analytics work; cleanup audited.
- Tests: Cloud smoke/security/fault tests.
- Evidence: Timestamped screenshots, URLs and cleanup inventory.
- Remaining risks: Requires explicit AWS and apply/destroy approval; latency/cost.

## Phase 8 — Original report, GitHub integration and viva readiness
- Files: `docs/report*, docs/diagrams/, approved GitHub repo`.
- Steps: Explain evidence; cite sources; verify links; acknowledge assistance; rehearse.
- Commands: ./scripts/check-local.sh; manually review report and rehearse.
- Acceptance: Rubric evidence complete; user can explain code.
- Tests: Evidence audit and timed viva.
- Evidence: Report, GitHub CI and viva presentation.
- Remaining risks: Remote push only with approval; no fabricated results.
