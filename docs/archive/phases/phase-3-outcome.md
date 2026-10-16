# Phase 3 outcome — 14 October 2026
Status: local implementation ready for review. Managed Cognito integration is implemented and verified with offline keys, but no real Cognito account flow has been exercised. Stop before Phase 4 until user review.

## Implemented locally
- Backend authentication supports explicitly enabled local developer identities or Cognito access tokens. Cognito mode validates RS256 signature, configured issuer, client_id, token_use, expiry, required human-user claims and administrator group. A fixed configured JWKS endpoint uses a bounded timeout and key caching; unavailable keys fail closed.
- Frontend managed signup, email confirmation, login and common SMS/email/TOTP/new-password challenges via the pinned Amplify SDK. These controls are disabled in default local mode. Tokens/refresh state use memory storage; refresh requires sign-in again. Profile preferences belong to the verified subject and cannot set roles.
- Administrator UI for attraction creation/update/retirement/restoration and full stored tier creation/edit/deactivation. Price/tier snapshots in existing bookings remain unchanged. Backend authorization protects all operations independently of UI visibility.
- All-time confirmed sales/revenue grouped by stable tier ID; daily arrivals count guests; ride totals group by attraction ID so renaming does not split totals. These operational views are not Metabase dashboards.
- Independently verifiable RS256 digital tickets contain booking reference, date, party size and an opaque HMAC owner tag. Booking alone receives the private signing key. Gate receives the public verification key and ownership-tag key, and needs no live booking lookup.
- Administrator gate validation and one full-party check-in per booking. Wrong-date, expired, forged, legacy, duplicate and wrong-party-size scans fail. Guests arriving are counted, not only booking records.
- Administrator ride events require a same-day gate check-in, a bounded guest count, and a verified open attraction. Stable event IDs deduplicate retries and reject changed input. Catalog failures fail closed for rides while gate check-in remains independent. Request IDs propagate to catalog calls.
- Owned visit and ride history, versioned PostgreSQL schemas, append-only visit service permissions, timestamped arrival/ride outbox records, and a repeatable local demonstration script.
- Booking/gate readiness checks their ticket keys and SQL revision. Three API processes are independently useful; the local runner no longer stops siblings when one service exits.

## Verification and limitations
See validation.md for actual command results. A live test stopped the booking process and successfully admitted a four-person party through the gate; the services were then restored. Actual Cognito signup/MFA/group provisioning, external Stripe test checkout, Docker, Kubernetes, Amplify hosting and AWS integration remain unverified. No new browser walkthrough was claimed for these administrator/account screens; frontend validation is TypeScript/build plus backend/HTTP contracts.

## Important policies and assumptions
- Asia/Colombo is the park timezone. Tickets admit only on the visit date, regardless of the preferred slot; slots are preferences, not capacity reservations.
- Full party arrives together; no partial arrivals/re-entry/cancellation/refunds are supported. These are explicit limitations, not inferred assignment rules. Introducing refunds requires a revocation strategy before allowing gate admission to trust signed tickets alone.
- Old Phase 2 HS256/ref-only QR payloads are rejected by gate. Re-open a confirmed digital ticket to issue the current RS256 format. Existing bookings and local access tokens remain intact. Never rotate/drop ticket/ownership keys casually; historical visit ownership relies on a stable tag key.
- Cognito JWT verification is offline once keys are cached. Logout/group changes/revocation are not a live denylist; existing signed access tokens can remain valid until expiry. Production should use short supported lifetimes and evaluate a denylist if immediate revocation is required.
- Profiles store only display name/language; gate stores pseudonymous owner tags, not names or email. Tags are still linkable personal data requiring protection. Local files/DB data stay ignored.
- Unsupported Cognito challenge/selection flows show a message rather than pretending sign-in succeeded. Verify the actual pool/client/MFA configuration in an approved cloud rehearsal.
- Ride status is checked just before insertion; catalog retirement can race with recording. There is no distributed transaction across services.
- Outbox records are durable but not yet published. SQS, worker projections, the five mandatory reporting queries, quiet hours and Metabase dashboards remain Phase 4.

## Manual review
1. Open http://localhost:5173 and refresh the running preview.
2. Generate `.venv/bin/python scripts/local-token.py --subject demo-admin --role admin`, privately copy the resulting token, connect it in Local development identity, then open Administrator.
3. Try catalog/tier management and inspect actual operational totals. Do not paste AWS keys or payment secrets.
4. Run `.venv/bin/python scripts/checks/tickets.py` while native DB/APIs/Vite run; then connect a token for `phase3-demo-visitor` and inspect My visits.
5. For a new manual gate scan after all preferred arrival slots have passed, run `.venv/bin/python scripts/checks/tickets.py --scenario manual --prepare-only`, view that visitor's current-day ticket, copy Local demo gate scan data, switch to the administrator identity, validate and admit the full party. This script explicitly seeds visit_date before a verified simulated payment; it is not a normal booking API bypass or a production workflow.
6. Review this outcome before Phase 4. Real Cognito connections still require explicit separate AWS approval; no cloud setup is requested automatically here.
