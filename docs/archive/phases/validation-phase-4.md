# Current validation — Phase 4, 14 October 2026

Local verification only. No AWS account connection, real payment, Terraform apply/destroy, Git commit or push performed by this phase. Historical records are in validation-phase-1.md, validation-phase-2.md and validation-phase-3.md.

| Check | Actual evidence | Limit |
|---|---|---|
| Automated suite | 96 passed, no skips; 10 new Phase 4 tests | Dedicated *_test PostgreSQL database; one upstream Starlette TestClient deprecation warning |
| Existing domains | All booking/payment, offline Cognito, profile, gate/ride, security, ownership and concurrency tests still pass | Actual Cognito and Stripe test-account delivery remain unverified |
| Local publication | Queue insertion and source acknowledgment rollback together; repeat publishing does not duplicate facts | PostgreSQL local transport, not an SQS emulator |
| Projection | Fact/dedupe/ack rollback/replay; changed-event conflict; six consumers count 20 messages once | Transaction rollback simulated; no database-node failure injection |
| Poison messages | Backoff, three-attempt dead letters, savepoint rollback and admin-only redrive verified | Redrive does not repair payload; retention policy pending |
| SQS adapter | Injected offline client: lost delete and failed send transaction replay safely | No AWS connection, IAM/redrive infrastructure or live SQS verification |
| Five metrics | Guest weighting, confirmed ticket counts, snapshot cents, rider/event counts, Colombo midnight, zero hours and ties tested | Provisional 09:00–18:00; reports use all history |
| DB permissions | Worker can update only source published_at, cannot read bookings; BI reads views but cannot read queue/bookings or write facts | Shared instance remains common failure domain |
| Frontend | TypeScript and production Vite build pass with protected Analytics tab | Interactive UI review pending after previous browser security rejection |
| Live native HTTP | Four readiness checks pass; reporting rejects anonymous access; all five stored reports return | Local auth and simulator only |
| Recovery demonstration | Processing disabled: three new events durable, source bookings 7 vs facts 6; restart drains and reconciles | Explicitly local demo records; no production statistics |
| Source reconciliation | 7 purchases / 98,000 cents / 28 booked guests; 4 arrivals / 16 guests; 3 ride events / 6 riders; pending/dead zero | Observed local snapshot; new activity can change totals |
| Metabase | Native OSS 0.58.35 on Java 21; real read-only reporting connection; all 7 saved SQL questions completed; rerun successful | Private local login; development-only H2 metadata; chart layout not interactively reviewed |
| Docker/CI | Compose and migration/worker Dockerfile configuration updated | Docker absent and remote CI not run; no container execution claim |

Reproduce with `scripts/local/database.py start`, `./scripts/check-local.sh`, native API/frontend runners and `scripts/checks/reporting.py`. See [Phase 4 outcome](phase-4-outcome.md) for Metabase and paused-worker commands. All Python scripts use `.venv/bin/python`. The provisioning rerun initially attempted setup again because Metabase retained a setup token; checking `has-user-setup` corrected the condition, and a repeat provision then passed. No failed run is counted as successful evidence.
