# Local validation evidence — 13 October 2026
Scope: Phase 0 and minimal Phase 1 only. No AWS identity lookup, payment call, Terraform apply/destroy, Git commit or GitHub push was performed.

| Check | Actual result | Practical limit |
|---|---|---|
| pypdf extraction | 13 PDFs, all pages processed; no empty assignment/lab/outline/schedule text pages | Four lecture cover pages empty; diagram-only content not visually reviewed |
| Python baseline | Isolated uv CPython 3.12.14 environment installed from pinned lock | System Python 3.14 not used for application verification |
| pytest | 24 passed | Health contract, correlation/privacy, invalid ID and absent domain route; no business/integration database tests yet |
| TypeScript + Vite | Passed; 15 modules transformed | Built using available Node 26.3.0; Node 22 container/CI baseline still needs execution |
| Live API HTTP | Four readiness requests passed on ports 8001–8004 | Actual Uvicorn processes; readiness is skeleton-only |
| Frontend proxy HTTP | Four /api/{service}/health routes passed through Vite | Development proxy only; Amplify production API configuration deferred |
| Browser inspection | Rendered shell and four responding health cards confirmed | Default browser viewport; full mobile/accessibility/e2e suite deferred |
| Python runtime dependency audit | pip-audit: no known vulnerabilities found in requirements.lock | Fully pinned dependencies scanned with --no-deps; advisory snapshot only |
| npm audit | Zero vulnerabilities reported | Registry advisories at this time; not a guarantee of security |
| YAML syntax | Compose, Amplify and CI files parsed | Parsing is not Docker Compose or GitHub execution |
| Shell syntax | bash -n scripts/check-local.sh passed | Cloud scripts intentionally not implemented in this phase |
| Git hygiene | Course PDFs/extracted text, .env, caches and state ignored; git diff --check passed | No commit/push; future commits still require review |
| Docker build/Compose/PostgreSQL/Metabase | Not run: Docker executable unavailable | Images, actual container startup, DB volume persistence and ARM64 support unverified |
| Minikube/kubectl/Terraform | Not run: executables unavailable | No deployment resources implemented yet |
| Cloud/GitHub deployment | Not run, per user boundary | All cloud integrations and CI remote execution remain unverified |

The first frontend build failed because TypeScript required declarations for the CSS import. Added frontend/src/vite-env.d.ts and reran successfully. Pytest reports one upstream Starlette warning recommending httpx2 for TestClient; all tests pass with the pinned httpx dependency. Review the supported client migration before expanding the test suite rather than suppressing this warning.

Reproduce local checks with `./scripts/check-local.sh`. Reproduce live HTTP with `.venv/bin/python scripts/run-local-services.py`, Vite in another terminal, and `.venv/bin/python scripts/smoke-local.py`. The test servers were stopped after verification. GitHub CI includes real container build/start/smoke steps, but has not run remotely. Docker and Kubernetes claims must remain pending until those checks execute successfully.
