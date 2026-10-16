# Implementation roadmap

The local MVP now uses one launcher for app startup/testing, local infrastructure rehearsal and source packaging. The user requested local completion of phases 7–9 on 15 October 2026. Phase 7's original AWS rehearsal remains pending; Minikube/offline Terraform are explicitly a local rehearsal, not live AWS evidence. Phase 8 report/viva materials and the user-requested Phase 9 handover are maintained below. Remote CI, managed auth/hosting and external payment delivery still need actual account verification.

## Phase 0 — Read sources, trace requirements, agree design
- Files: `docs/*.md`.
- Steps: Extract PDFs; map p1–4 and rubric; select SQL; record risks.
- Commands: Read docs/assignment/requirements.md and docs/architecture/decisions.md.
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
- Evidence: Record real outputs in docs/results/local-validation.md.
- Remaining risks: No business/auth/payment/pipeline functionality.

## Phase 2 — Catalog, stored tiers, booking and test-payment domain
- Files: `services/attractions-service/, services/booking-service/, frontend/`.
- Steps: Migrations/seeds; integer cents; validation; idempotency; signed webhooks; QR/history.
- Commands: scripts/local/database.py start; scripts/db_migrate.py --seed; scripts/local/services.py; scripts/checks/payments.py (run with .venv/bin/python).
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
- Commands: scripts/local/database.py start; scripts/local/services.py; scripts/run-metabase.py; scripts/provision-metabase.py; scripts/checks/reporting.py (all with .venv/bin/python).
- Acceptance: Five mandatory metrics query persisted facts.
- Tests: Replay/crash/reconciliation/timezone tests.
- Evidence: Disabled-consumer backlog and restart reconciliation passed; seven Metabase SQL questions executed. See docs/archive/phases/phase-4-outcome.md.
- Remaining risks: Actual SQS/cloud integration and interactive chart review pending; provisional opening hours; shared database failure domain and retention.

## Phase 5 — Minikube and failure/scale demonstrations
- Files: `infrastructure/kubernetes/{base,local}, tests/`.
- Steps: Namespace/config/secret/probes/resources; Services; HPA; blue-green.
- Commands: scripts/local-kubernetes.py start/build/deploy/verify/forward; scripts/checks/cluster.py; scripts/demo-kubernetes.py (all with .venv/bin/python).
- Acceptance: Discovery, scale, self-heal and rollback demonstrable.
- Tests: Fault injection/load; readiness failure and recovery.
- Evidence: Real pod replacement, live business/analytics flow, worker/DB recovery, blue-green switch/rollback and actual CPU HPA 2→3→2 verified; see docs/archive/phases/phase-5-outcome.md.
- Remaining risks: Single-node/shared-DB failure domain; provisional local resources; cloud gateway/security remain later work.

## Phase 6 — Real Terraform and lifecycle scripts
- Files: `infrastructure/terraform/, infrastructure/kubernetes/aws/, scripts/`.
- Steps: Pinned providers/modules, secure states, least privilege, stage core/edge/workloads; guard apply/destroy.
- Commands: scripts/validate-cloud.py (with .venv/bin/python); guarded cloud.py/preflight/deploy/verify/destroy commands only after account/action approval.
- Acceptance: Real scripts show target/plan/cost, refuse unapproved apply/destroy; no fake success.
- Tests: Static validation and script failure-path checks.
- Evidence: Four provider-valid mocked plans, local cloud manifest/TLS/Helm checks, refusal tests and actual lifecycle code; live plans remain Phase 7.
- Remaining risks: Real account/region/domain/versions/prices/permissions and all managed integration/cleanup remain unverified. See docs/archive/phases/phase-6-outcome.md.

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

## Phase 7 local rehearsal — development substitute for cloud rehearsal
- Command: `./start.sh infra-test`.
- Scope: offline Terraform validation/mocks; actual local image build/deploy; visitor/admin/password/reference flow; self-healing; blue-green rollback; worker backlog recovery; DB readiness/persistence; real HTTP HPA scale-up/down; final reconciliation.
- Evidence: `docs/results/evidence/local-infrastructure.json` records **14 passing stages** on 15 October 2026, including 46,964 successful requests/zero failures and HPA 2→3→2. Two failed prior attempts are archived alongside it. Only `status: passed` is completion evidence.
- Local app access: `./start.sh infra`; stop with `./start.sh infra-stop`.
- Remaining original Phase 7 work: live account/region/cost/plan review, AWS integration, hosted Cognito/Amplify, Stripe delivery and audited cleanup. No AWS operation is authorized by a local command.

## Phase 8 local report and viva preparation
- Artifacts: `docs/assignment/report.md`, `docs/viva.md`, `docs/local/demo.md`, `docs/local/kubernetes.md`.
- Verification: `./start.sh test`; actual infrastructure evidence linked from the report.
- CI: existing workflow extended to produce the source-only handover artifact after checks. Git remote is configured; no remote workflow execution is claimed.
- Remaining: student's personal review, screenshots, explanation rehearsal, submission details, remote CI evidence and academic submission.

## Phase 9 — Clean local handover (added for the user's request)
- Command: `./start.sh package`.
- Output: `tmp/handover/wonderland-mvp.zip` plus SHA-256 checksum; source file hashes are inside `HANDOVER-MANIFEST.json`.
- Includes: MVP code, report, guides and optional assignment infrastructure.
- Excludes: private credentials/course PDFs, databases, installed dependencies, generated builds, Terraform states/plans and symlinks.
- Acceptance: ZIP integrity/privacy tests pass and a fresh checkout follows the documented one-time dependency setup. No data deletion, cloud deployment or remote publishing occurs.
