# Wonderland Theme Park
SE6020 individual MSc cloud-native booking and analytics project. Viva: 8 November 2026.

**Current scope: Phase 3 local implementation, ready for review.** Catalog, stored pricing, booking, simulated payment, RSA QR tickets, profiles, administrator management, gate arrivals, ride usage and owned histories are implemented. Cognito signup/login/MFA UI and backend JWT verification are prepared and offline-tested; actual AWS authentication is unverified. Local mode still uses signed developer tokens.

No AWS account was contacted and no cloud resources, real payments, commits or pushes were made by this work. Analytics worker remains a skeleton; SQS/Metabase reporting is Phase 4. Docker configuration is prepared but execution remains unverified because Docker is absent.

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
  analytics-worker/               Health-only skeleton; Phase 4
wonderland_common/                Shared config, identity validation, DB and web middleware
analytics/queries/                Reserved for Phase 4 reporting
infrastructure/
  local/Dockerfile.migrate         One-shot local migration/seed container
  terraform/{bootstrap,demo,modules}/  Reserved for Phase 6
  kubernetes/{base,local,aws}/         Reserved for Phase 5/6
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

Original course materials and credentials remain private. Understand and explain each change, cite sources and acknowledge assistance under SLIIT policy. Stop here for Phase 3 review before implementing the analytics pipeline and Metabase reporting in Phase 4.

## Administrator and visit demonstration
Generate a private local administrator token with `.venv/bin/python scripts/local-token.py --subject demo-admin --role admin`, connect it in the page and open Administrator. The backend checks the role independently. Use `.venv/bin/python scripts/smoke-phase3.py` for a repeatable local arrival/ride scenario; connect a token for `phase3-demo-visitor` to view that history. Real Cognito login stays disabled until explicitly approved and configured. See docs/phase-3-outcome.md for manual gate scanning and legacy-ticket notes.
