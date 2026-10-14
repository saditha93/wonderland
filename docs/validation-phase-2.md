# Phase 2 validation evidence — 14 October 2026

Scope: local Phase 2 only. No AWS connection, Terraform apply/destroy, external payment request, Git commit or GitHub push was performed. Historical foundation evidence is retained in validation-phase-1.md.

| Check | Actual result | Limit |
|---|---|---|
| PostgreSQL | Homebrew PostgreSQL 17.11; isolated project cluster, SCRAM, loopback port 55432 | Native execution; Docker/RDS unverified |
| pytest | 61 passed, one upstream TestClient deprecation warning | Dedicated real PostgreSQL test database; no skipped integration cases in this run |
| Concurrent booking commands | Six requests with same owner/key produced one booking | Correctness test, not a capacity benchmark |
| Concurrent payment delivery | Six signed deliveries produced one confirmation/event | At-least-once queue consumption not implemented |
| Atomic failure recovery | Forced outbox insert failure rolled back payment-event/booking changes; retry succeeded | Actual PostgreSQL transaction test |
| Validation and privacy | Guest/date/tier validation; client price rejected; ownership/admin guards; invalid/expired identities; secret-safe logs/config errors | Cognito and account profiles still Phase 3 |
| Payment security | Raw-payload signatures, freshness, live-mode rejection, amount/currency/session matching, replay and conflicting event ID tests passed | Local signed simulator plus SDK-based Stripe signature checks; no provider account contacted |
| Stripe adapter/breaker | Stored price/provider idempotency/SDK request shape checked with mocked network; open/half-open recovery and pending-on-outage passed | Actual Stripe Checkout and webhook delivery unverified |
| Ticket | Confirmed-only ticket access, signed QR claims and independent key/audience verified | Gate scanning/revocation is Phase 3; no cancellation/refund policy yet |
| Database migration/seed | Numbered migrations and repeated seeds succeeded without overwriting edited prices | Future schema changes must use new numbered migrations |
| Role permissions | Both live service roles accessed own schema and were denied other schema usage | Shared database instance is still a failure domain |
| Persistence | Booking remained stored after SQLAlchemy engine disposal/reconnection; project database restarted with data preserved | Full host disaster recovery not tested |
| Frontend | TypeScript and Vite production build passed (16 modules) | Available Node 26; Node 22 image/CI baseline not executed here |
| Real HTTP | Four health checks and catalog -> tiers -> booking -> retry -> signed local payment -> signed ticket/history passed through Vite | Requires native DB/APIs/Vite; simulator only |
| Final browser recheck (14 October) | Blocked by browser security policy, which reported a URL-protocol restriction | No workaround attempted; earlier walkthrough and fresh HTTP checks are recorded separately |
| Browser walkthrough | Catalog search/details, token-required booking boundary, signed visitor connection, Family/four guests/$140, simulated payment, QR and confirmed history verified | Recorded during Phase 2 work on 13 October; full accessibility/device suite deferred |
| Python dependency audit | pip-audit found no known vulnerabilities in pinned runtime list | Advisory snapshot; --no-deps used because all transitive runtime versions are pinned |
| npm audit | Zero vulnerabilities reported | Advisory snapshot only |
| YAML/shell/Git hygiene | Compose/CI/Amplify YAML parsed; shell syntax valid; git diff --check clean; private sources/config ignored and untracked | YAML parsing is not Docker/GitHub execution |
| Docker/Compose/Metabase | Not executed: Docker absent | Images, Compose migration ordering, volume behavior and Metabase startup still need actual checks |
| Kubernetes/AWS/GitHub | Not executed | No deployments or fabricated cloud evidence |

Reproduce with `.venv/bin/python scripts/local-postgres.py start` then `./scripts/check-local.sh`. Start APIs and Vite for `scripts/smoke-local.py` and `scripts/smoke-phase2.py`. The latter writes a local demo booking for demo-visitor, while pytest truncates only the separate *_test database. The development database and test database are distinct.

The initial Stripe SDK signature test exposed the SDK's Event object conversion requirement; converting the verified event with to_dict() fixed it and the test passes. An initial frontend build issue from Phase 1 is documented in the historical evidence. The current Starlette warning recommends httpx2; it remains visible rather than suppressed, and all tests pass using the pinned client.

No total mark, production readiness, cloud integration or real payment-provider completion is claimed. Phase 2 local behavior is verified; external Stripe test service and Docker execution remain explicit acceptance gaps.
