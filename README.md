# Wonderland Theme Park
SE6020 individual MSc cloud-native booking and analytics project. Viva: 8 November 2026.

**Current scope: Phase 5 local Kubernetes implementation, ready for review.** Catalog, stored pricing, booking, simulated payment, RSA QR tickets, profiles, administrator management, gate arrivals, ride usage and owned histories are implemented. Cognito signup/login/MFA UI and backend JWT verification are prepared and offline-tested; actual AWS authentication is unverified. Local mode still uses signed developer tokens.

No AWS account was contacted and no cloud resources, real payments, commits or pushes were made by this work. Durable local event processing, reporting views, the Analytics tab and private Metabase dashboards are implemented and verified. SQS adapter is offline-tested; actual AWS SQS is unverified. Application images now build and run in the named local Minikube cluster. Compose configuration validates; its separate runtime was not exercised.

## Quick local start (native PostgreSQL)
Python 3.12 and Node.js 22.12+ required. This Mac now has Homebrew PostgreSQL 17.11 installed; the project uses its own SCRAM-authenticated loopback cluster, not a Homebrew background service.

```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
.venv/bin/python scripts/local-postgres.py start
./scripts/check-local.sh
.venv/bin/python scripts/run-local-services.py
```

In another terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open http://localhost:5173. To book, run `.venv/bin/python scripts/local-token.py` privately in your terminal and paste the resulting one-hour token into **Local development identity** on the page. This deliberately displays a developer token to you; never share, log, or commit it. Public attractions/prices need no token. Tokens stay in browser memory and disappear on refresh.

A real local HTTP demonstration is available with `.venv/bin/python scripts/smoke-phase2.py` while servers run. It uses the local simulator, stores a Family booking for `demo-visitor` and validates its signed ticket. Repeated calls with the same command reuse the booking. See [development guide](docs/development.md) for setup, stop/reset instructions, Compose and optional Stripe test configuration.

## Project guide
- [Phase 5 outcome](docs/phase-5-outcome.md), [local Kubernetes commands](docs/local-kubernetes.md)
- [Phase 4 outcome, Metabase and recovery instructions](docs/phase-4-outcome.md)
- [Phase 3 outcome and limitations](docs/phase-3-outcome.md), [Cognito integration boundary](docs/cognito-integration.md)
- [Requirements traceability](docs/requirements-matrix.md), [teaching alignment](docs/lecture-alignment.md)
- [Architecture](docs/architecture.md), [decisions](docs/architecture-decisions.md), [patterns](docs/design-patterns.md)
- [Validation evidence](docs/validation.md), [risks](docs/requirements-risks.md), [cost](docs/cost-management.md)
- [Roadmap](docs/implementation-roadmap.md), [viva checklist](docs/viva-checklist.md)

## Structure
```text
frontend/                         React/TypeScript catalog, booking, payment, history, ticket UI
services/
  attractions-service/            Catalog API, protected CRUD/retirement, SQL migration
  booking-service/                Tiers, pricing, booking, test payment, tickets, SQL migration
  gate-ride-service/              Public-key ticket checks, arrivals, rides and visit history
  analytics-worker/               Durable queue, deduplication, projections and protected reports
wonderland_common/                Shared config, identity validation, DB and web middleware
analytics/queries/                Stored SQL for five required metrics and supporting queries
infrastructure/
  local/Dockerfile.migrate         One-shot local migration/seed container
  terraform/{bootstrap,demo,modules}/  Reserved for Phase 6
  kubernetes/{base,local,demos}/       Local workloads, storage, HPA and green release
  kubernetes/aws/                    Reserved for Phase 6
scripts/                          Native PostgreSQL, migration, token, Compose and verification tools
tests/                            Health/security and real PostgreSQL domain integration tests
docs/                             Requirements, design, phase outcomes and evidence
  diagrams/                       Six proposed Mermaid diagrams
  course-materials/               Private ignored PDFs and extracted text
secrets/                          Ignored mode-0600 local configuration (never publish)
tmp/                              Ignored local PostgreSQL data and temporary files
.github/workflows/ci.yml           Tests, frontend, container build/start checks (not run remotely)
amplify.yml                       Frontend build configuration; hosting not deployed
```

Original course materials and credentials remain private. Understand and explain each change, cite sources and acknowledge assistance under SLIIT policy. Stop here for Phase 5 review before Terraform and cloud lifecycle implementation in Phase 6.

## Administrator and visit demonstration
Generate a private local administrator token with `.venv/bin/python scripts/local-token.py --subject demo-admin --role admin`, connect it in the page and open Administrator. The backend checks the role independently. Use `.venv/bin/python scripts/smoke-phase3.py` for a repeatable local arrival/ride scenario; connect a token for `phase3-demo-visitor` to view that history. Real Cognito login stays disabled until explicitly approved and configured. See docs/phase-3-outcome.md for manual gate scanning and legacy-ticket notes.

## Stored analytics and Metabase

Open **Administrator → Analytics** using an administrator token. The native private Metabase dashboard, when started, is at [localhost:3000/dashboard/2](http://localhost:3000/dashboard/2); login details are in private `secrets/metabase.json`. See the Phase 4 outcome for a fresh installation and for the paused-worker recovery demonstration. Run `.venv/bin/python scripts/smoke-phase4.py` to reconcile stored reporting totals with actual local purchases, arrivals and rides. Production builds require public `VITE_METABASE_URL` to show the Metabase link.

## Local Kubernetes application

The isolated Kubernetes app is at [localhost:5180](http://localhost:5180) while `scripts/local-kubernetes.py forward` runs. It uses separate demo data and signing keys; generate developer tokens with `--env-file secrets/kubernetes.env`. See the local Kubernetes guide for builds, ordered deployment, recovery/scaling demonstrations and stopping the named VM without deleting data.
