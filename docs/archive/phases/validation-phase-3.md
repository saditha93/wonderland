# Current validation — Phase 3, 14 October 2026
Local verification only. No AWS account access, Terraform apply/destroy, actual Cognito account request, external payment call, Git commit or push occurred. Historical records are in validation-phase-1.md and validation-phase-2.md.

| Check | Actual evidence | Limit |
|---|---|---|
| PostgreSQL integration suite | 86 passed, no integration skips; one upstream TestClient deprecation warning | Dedicated *_test database; no development data truncation |
| Original booking/payment flow | Existing domain tests continue passing after RSA ticket migration | External Stripe test-account delivery remains unverified |
| Cognito verification | Real RSA/JWK verification with offline keys; issuer/client/token_use/expiry/group/audience/algorithm checks; unknown key and key-fetch failure tests | No real AWS pool used |
| Local profiles/admin APIs | Own profile only; role changes rejected; protected catalog/tier lifecycle and snapshot-preserving changes tested | New UI forms have build/API-level validation, not a fresh browser walkthrough |
| Gate arrivals | Six concurrent scans admit one party; duplicate scans return 409; full guest counts; wrong date/forgery/legacy denied | Full-party policy; no partial arrival/re-entry/refund/revocation |
| Ride usage | Check-in required, date/count bounds, concurrent event deduplication, changed-payload conflict, catalog fail-closed behavior | Catalog status and event insertion are not a distributed transaction |
| Atomicity | Arrival and ride outbox failures roll back domain writes; retry succeeds | Queue/worker delivery is Phase 4 |
| Visitor history | Owned visits/rides only; different visitor receives no other records | Bounded lists; pagination future |
| Stable-ID totals | Renaming tiers/attractions does not split totals; confirmed snapshot amounts counted | Operational SQL, not Metabase reporting |
| Key readiness | Missing gate keys yield readiness 503 while liveness stays 200; booking/gate use RSA key validation | Cloud secrets distribution/rotation unverified |
| Live local HTTP | Profile, admin denial, confirmed signed ticket, four-guest arrival, duplicate scan, two-rider event and owned history passed through Vite | Local simulator and PostgreSQL only |
| Live service isolation | Stopped booking process; gate independently admitted four guests and stayed ready; all services restored | Shared DB remained online; not a node/DB failover test |
| Database roles | Each of attractions/booking/visits can use only its own schema; no cross-schema usage | Local privileged migrator excluded from API processes; cloud IAM pending |
| Frontend | TypeScript and Vite production build passed; public/admin data loads degrade independently | Available Node 26; Node 22 image baseline and interactive MFA/UI review unverified |
| Dependency audits | pip-audit: no known runtime vulnerabilities; npm audit: zero vulnerabilities reported | Advisory snapshot only |
| YAML/Git hygiene | Compose/CI/Amplify YAML parsed; private files ignored/untracked; diff whitespace clean | Docker absent, so no claim of container execution; GitHub CI unrun |
| Managed cloud integration | Not executed, per approval boundary | Cognito/Amplify/Gateway/EKS/Terraform remain future approved verification |

Reproduce native checks with `.venv/bin/python scripts/local/database.py start` and `./scripts/check-local.sh`. Start the local APIs and Vite for `scripts/checks/containers.py`, `scripts/checks/payments.py` and `scripts/checks/tickets.py`. Repeatable scenario keys/event IDs prevent retries from creating duplicate purchases/arrivals/rides. Different named demo scenarios intentionally create separate local bookings.

The first expanded run exposed two test-fixture issues (restoring a disabled booking DB and converting an RSA public key to JWK). They were fixed; this record does not count those failed runs as passes. One upstream Starlette TestClient/httpx deprecation warning remains visible. No cloud success, mark allocation or production readiness is claimed.
