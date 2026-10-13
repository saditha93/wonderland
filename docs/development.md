# Local development and verification
Use Python 3.12 and Node.js 22.12+ (Node 22 LTS is the container/CI baseline). Dependency versions are pinned in requirements.lock, requirements-dev.lock and frontend/package-lock.json. Base images are tagged, not digest-pinned yet; verify ARM64 support and digest-pin during deployment hardening. No AWS CLI, credential setup or payment account is needed for this phase.

## Without Docker
From the repository root:

```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
./scripts/check-local.sh
.venv/bin/python scripts/run-local-services.py
```

In a second terminal run `npm --prefix frontend run dev -- --host 127.0.0.1`. Visit http://localhost:5173. In a third terminal run `.venv/bin/python scripts/smoke-local.py`. API docs are on ports 8001–8004 at `/docs`. Ctrl-C stops the service runner and all four children; stop Vite with Ctrl-C separately. The service runner is local-only and does not use PostgreSQL yet.

Without uv, create a Python 3.12 venv and use `.venv/bin/python -m pip install -r requirements-dev.lock`. Do not use the system Python 3.14 environment in place of the documented baseline.

## Docker Compose
Install/start Docker Desktop or an equivalent Docker engine and Compose plugin manually first. No cloud instances are required (Mac local development intentionally adapts the EC2-hosted lab).

```bash
cp .env.example .env
# Edit .env and replace the local-only database password.
docker compose --env-file .env config --quiet
docker compose --env-file .env up --build -d --wait
.venv/bin/python scripts/smoke-local.py
```

Frontend: http://localhost:5173. APIs: http://localhost:8001/health through port 8004. PostgreSQL: localhost:5432, database/user from .env. All published ports bind loopback. API skeletons have no database dependency; a healthy API does not claim healthy persistence. The PostgreSQL container has its own pg_isready check. Database business schemas and migrations are P2, not silently initialized here. The owner role in this foundation is local-only; add separate service roles before real domain integration.

Stop containers with `docker compose down`; named data volumes remain. Changing POSTGRES_PASSWORD in .env does not change the password in an existing initialized PostgreSQL volume. To discard local data deliberately, `docker compose down --volumes` deletes PostgreSQL and Metabase local volumes; only use it when you intend to reset them.

## Optional Metabase preparation
`docker compose --profile analytics up -d` starts http://localhost:3000. Complete its local admin setup manually. From Metabase, PostgreSQL host is `postgres`, port 5432 (not localhost). Domain reporting schema/read-only role/dashboard queries are P4; do not claim any dashboards exist now. Metabase uses a volume-backed embedded H2 metadata database for this development-only foundation. Replace this with a separate PostgreSQL metadata database before AWS deployment. No sample hardcoded metrics or fake booking data are supplied.

## CI and security boundary
.github/workflows/ci.yml runs tests, type/build checks, Compose configuration, real image builds, and HTTP container smoke tests when pushed to an approved repository. The workflow has not run on GitHub here. No cloud deploy job is created in this phase; later OIDC/protected environment controls must require approval. Do not push, create AWS resources, or run Terraform apply/destroy until explicitly authorized. Course PDFs, extraction output, .env, Terraform state/plans and private secrets are ignored. `.env.example` contains a placeholder, not a usable production credential.

## Learning walkthrough
Read a service app/main.py: Settings reads environment; response models validate health output; middleware attaches a safe ID and logs duration; routes check only process/skeleton state. Each Dockerfile copies just its service and installs the common pinned runtime list. Compose DNS names match Vite proxy targets. In React, the health cards fetch actual endpoints, show failure when unavailable and never pretend to provide booking/authentication. Health cards are a development shell, not the final visitor UX.
