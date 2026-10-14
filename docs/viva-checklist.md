# Viva checklist — 8 November 2026
No completion boxes are checked for features not implemented. Assignment p4 rubric governs this checklist. Confirm exact time slot and allowed provisioning wait with lecturer. Assignment requires stack execution during viva; pre-created infrastructure alone is insufficient evidence.

| Weight | Demonstration checklist | Evidence to retain |
|---|---|---|
| Report 15% | Original architecture, sources, ADRs, NFR and limitations | Submitted report and diagrams |
| Microservices 20% | Catalog; stored pricing; booking, test payment, ticket; admin; gate and ride events | Tests, API requests, independent images |
| Kubernetes + API Gateway 20% | External gateway routes; Services/DNS; probes; replicas/load balancing; pod self-heal; blue-green rollback | kubectl output, gateway request, logs and failure timeline |
| React + Amplify + Cognito 15% | Register/login; visitor and admin; booking/history; forbidden cross-user/admin calls | Hosted UI and backend 403 evidence |
| Monitoring/visualization 10% | Real Metabase facts: daily guests, sales/tier, revenue/tier, popular rides, peak/quiet hours | Query results and dashboard matching seed totals |
| IaC 10% | Target identity/region, plan, cost, explicit approval, staged live deploy, health, approved cleanup | Plan/apply outputs, elapsed time, cleanup inventory |
| Integration 10% | Real approved GitHub repo; CI; end-to-end data flow | Commit link, workflow and scenario results |

## Rehearsal order (future)
1. Confirm non-root identity, region, budget, inputs, images and Terraform plan; request explicit apply approval.
2. Start IaC; explain persistent versus temporary states while infrastructure provisions.
3. Deploy workloads, migrate/seed; publish frontend with current API config. Never print success before verification.
4. Register visitor, browse, book a family ticket, pay in test mode, show reference/QR and booking history.
5. Admin adjusts price; confirm existing snapshot unchanged. Check in family: four guests, one booking. Repeat scan is rejected.
6. Record rides across hours and show all five Metabase metrics; replay one event without double counting.
7. Show pod deletion/self-heal, replicas/discovery/load balance, breaker/pending payment, queued analytics outage recovery and blue-green rollback.
8. Show GitHub/CI and explain limitations; show destruction plan, get separate explicit destroy approval, clean workloads/edge/core and audit costs.

## Questions and answer prompts
- Why Kubernetes / EKS rather than ECS? Mandatory Kubernetes assessment; portable orchestration and labs; EKS adds cost and management.
- Why microservices? Independently deployable boundaries and isolated failure; additional networking/data consistency costs.
- Why Terraform? Versioned reproducible lifecycle, plan review and separate states; flag assignment wording conflict.
- How does discovery work? Stable Service DNS points to healthy pod endpoints; IPs may change.
- How does self-healing work? Controller reconciles desired replicas; probes determine readiness/liveness; DB availability is separate.
- What is a circuit breaker? Closed/open/half-open states avoid repeated dependency calls; failed payment stays pending.
- Why gateway? One external entry for routes and auth; extra hop/cost; backends still authorize.
- What happens if a service fails? Gate can verify confirmed tickets independently; analytics buffers; shared DB is still a limitation.
- How prevent duplicate booking/payment? User-bound idempotency key plus payload hash, unique provider events, transactional conditional confirmation; capacity locking only if capacity rules agreed.
- How does analytics work? Outbox -> at-least-once queue -> deduplicated SQL projection -> read-only Metabase; report lag.
- How secure? Verified Cognito tokens, admin/ownership enforcement, TLS, encryption, narrow IAM/DB roles, verified test webhook and secret redaction.
- How reduce cost? Local development, timed temporary EKS/RDS, no idle NAT, bounded retained storage, verified cleanup.
- What do apply/destroy do? Reconcile resources described by state/plan; dependency ordering and controller-owned resources require staged cleanup.
- Limitations? Single DB failure domain, small demo capacity, eventual reporting lag, revocation policy, no AWS proof until approved tests.

Explain only implemented behavior as implemented. Keep AI/other assistance acknowledgements aligned with SLIIT policy; personally rehearse code walkthroughs.

## Current Phase 2 rehearsal boundary
Locally verified: catalog/suitability, stored tiers/price snapshots, pending booking/idempotency, signed local test-payment event, confirmed QR ticket and own booking history. Developer identity is not Cognito login. Stripe test-account delivery, admin screens, gate/ride history, dashboards, Kubernetes/gateway, IaC and cloud evidence remain pending. See phase-2-outcome.md and validation.md. Never present the simulator as a real payment provider integration.

## Current Phase 3 rehearsal boundary
Locally verified: profile ownership, administrator API guards, tier lifecycle/snapshots, signed RSA gate tickets, full-party unique arrivals, live booking-process outage admission, ride retries, visitor history and operational guest/sales/rider totals. Administrator/account screens are built and await interactive review. Cognito SDK/verifier is prepared and offline-tested; do not claim AWS login/MFA is verified. Metabase, queue worker, Kubernetes/gateway, IaC and cloud evidence remain pending.
