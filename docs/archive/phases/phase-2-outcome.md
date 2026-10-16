# Phase 2 outcome — 14 October 2026
Scope authorized by user: continue to Phase 2, locally. Stop for review before Phase 3.

## Implemented
- Catalog list/search/detail with stored suitability/status; protected create/update/retire API and soft retirement.
- Four database-backed initial tiers: Individual 1/$40, Couple 2/$75, Family up to 4/$140, Group up to 5/$165. Protected price-update API; administrator screens/tier management are Phase 3.
- Booking command validation, visitor ownership, user-bound idempotency keys with payload hashes, concurrent duplicate protection, integer-cent price/tier snapshots and history.
- Local signed payment simulation and Stripe test adapter; verified webhook payloads, replay/collision checks, amount/currency/session matching, atomic confirmation plus one durable outbox event.
- Signed QR ticket for confirmed bookings, no personal information in QR claims; separate ticket key/audience, expiry at end of visit day.
- Responsive visitor catalog, booking, payment, history and ticket pages. Identity is a clearly labelled local developer tool, not Cognito registration/login.
- PostgreSQL versioned SQL migrations and non-destructive seeds, restricted service roles, isolated test database, actual dependency readiness checks.
- Shared package for middleware/config/auth/database; each service remains a separate process/image. This introduces a shared code release dependency; it is not a runtime call between services.
- Updated Compose/CI migration ordering and native local setup/run/verification scripts.

## Evidence
See docs/results/local-validation.md for current checks and limitations. PostgreSQL-backed tests include simultaneous duplicate commands/webhooks and a failed-outbox write proving confirmation rollback. Live HTTP tests go through Vite's proxy. The earlier browser walkthrough created a four-person Family booking, reviewed $140, simulated verified payment, displayed the signed QR and retrieved confirmed history. That scenario used disposable local data and no external payment service.

## Assumptions and trade-offs
- Timezone Asia/Colombo; provisional slots 09:00,12:00,15:00; dates today through 365 days ahead; no invented park capacity.
- Individual/Couple exact count, Family/Group minimum 1 and maximum 4/5 pending requirements clarification.
- PostgreSQL schemas share an instance/failure domain. Separate API roles cannot access each other's schemas. Local migration owner is privileged and never passed to API children.
- Pending checkout creation holds a row lock during bounded external calls; this simplifies concurrent checkout creation but can occupy a DB connection while the provider responds. Refine with a durable payment-attempt state if load warrants it.
- Outbox is persisted but not published yet; at-least-once SQS processing/reporting is Phase 4.
- Local sandbox confirmation is intentionally possible only in local/test mode. It is not proof that Stripe works, and these identities are not deployable managed authentication.
- Checkout-session expiry/replacement, refunds/cancellation and ticket revocation are not implemented; expired checkout URLs currently require an explicit future recovery design.
- History and catalog currently cap returned records at 100; pagination remains future work.

## Manual review
1. Review this outcome, requirements matrix and remaining risks.
2. Start native PostgreSQL/APIs/Vite using docs/development.md if stopped.
3. Generate your own local visitor token and try catalog -> Family booking -> local test payment -> QR -> history.
4. Optionally configure Stripe test credentials privately and verify actual provider delivery later; no production payments.
5. Review before starting Phase 3: Cognito/auth/profile, administrator screens and tier management, gate check-ins, ride usage and visit history. AWS connections still require explicit separate authorization.
