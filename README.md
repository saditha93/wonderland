# Wonderland Theme Park
SE6020 individual MSc cloud-native booking and analytics project. Viva: 8 November 2026.

**Current scope: Phase 0 design and minimal Phase 1 local foundation.** No booking, authentication, payment, gate processing, analytics pipeline or cloud deployment is implemented yet. Four independent FastAPI skeletons expose health endpoints; React displays live local health responses. PostgreSQL and optional Metabase are configured in Compose. No AWS account was contacted and nothing was pushed or committed by this work.

Start with [requirements](docs/requirements-matrix.md), [teaching alignment](docs/lecture-alignment.md), [architecture](docs/architecture.md), [decisions](docs/architecture-decisions.md), [risks](docs/requirements-risks.md), [cost](docs/cost-management.md), [roadmap](docs/implementation-roadmap.md), [viva checklist](docs/viva-checklist.md) and [validation](docs/validation.md).

## Quick local start (no Docker required)
```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
./scripts/check-local.sh
.venv/bin/python scripts/run-local-services.py
```
In another terminal: `npm --prefix frontend run dev -- --host 127.0.0.1`. Open http://localhost:5173. Stop both processes with Ctrl-C.

For Docker/PostgreSQL/Metabase instructions, environment setup, reset behavior and learning notes, see [development guide](docs/development.md). Service ports: 8001 attractions, 8002 booking, 8003 gate/ride, 8004 analytics skeleton. `/health/ready` is explicitly skeleton-only until dependencies are implemented.

## Structure
```text
frontend/                         React + TypeScript + Vite + Tailwind shell
services/
  attractions-service/            Independent health-only FastAPI image
  booking-service/                Independent health-only FastAPI image
  gate-ride-service/              Independent health-only FastAPI image
  analytics-worker/               Inert health-only worker foundation
analytics/queries/                Reserved for Phase 4 SQL
infrastructure/
  terraform/{bootstrap,demo,modules}/  Reserved for Phase 6
  kubernetes/{base,local,aws}/         Reserved for Phase 5/6
scripts/                          Local checks, service runner, HTTP smoke
tests/                           Cross-service API contract/privacy tests
docs/                             Requirements, design, risks, roadmap, evidence
  diagrams/                       Six proposed Mermaid diagrams
  course-materials/               Private ignored PDFs and extracted text
.github/workflows/ci.yml           Local checks/build/smoke workflow
amplify.yml                       Static frontend build configuration (not deployed)
docker-compose.yml                Loopback-only local dependencies and services
```

Original course PDFs and extracted text stay private. Public documents paraphrase and cite source pages. Follow SLIIT academic integrity policy, acknowledge assistance appropriately, and be able to explain each implementation decision. Review this phase before beginning Phase 2.
