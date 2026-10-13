# Proposed architecture — Phase 0 baseline
Status: proposed cloud design with a locally implemented Phase 2 subset. Catalog and booking domains, stored prices, local test-payment confirmation, signed tickets and booking history now run against PostgreSQL. Signed developer identities are local-only; managed login, gate operations, worker consumption and all AWS integration remain future work. See phase-2-outcome.md.

React/TypeScript/Vite/Tailwind will be hosted by Amplify. Cognito supplies user authentication; each backend validates JWT signature via JWKS, issuer, expiry, access-token client_id/token_use and admin group or visitor ownership. API Gateway HTTP API provides external routes and JWT authorization. A VPC link connects to an internal ALB managed by the AWS Load Balancer Controller. ALB path routing targets EKS services/pods. Map away API Gateway stage prefixes. Explicit HTTPS private integration requires a certificate/name and tlsConfig; include pod TLS or a TLS proxy if claiming encryption over every hop. No public service bypass of authorization is permitted.

Source: [AWS private HTTP integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html), checked 13 October 2026. Domain/certificate provisioning and verified end-to-end TLS remain P6 gates.

| Service | Owns | Deployable boundary | Planned database permissions |
|---|---|---|---|
| Attractions | Catalog and retirement | Own process, image and Deployment | attractions schema read/write only |
| Booking | Tiers, price snapshots, bookings, payments, ticket issuance | Own process, image and Deployment | booking schema read/write only |
| Gate/ride | Ticket validation, arrivals, ride events, visit history | Own process, image and Deployment | visits schema read/write only |
| Analytics worker | Event deduplication and reporting projection | Worker plus health server in own Deployment | reporting writes, outbox access only where explicitly granted |
| Metabase | Dashboards, query metadata | Local optional profile; private AWS deployment later | reporting SELECT; separate metadata database |

A single PostgreSQL instance lowers demo cost, but separate schemas and roles enforce ownership. This shares a database failure domain; it is not full independent storage. Phase 2 implements attractions and booking schemas plus separate restricted API roles. The development-only owner is reserved for migrations/seeds and is not passed to API processes. Metabase never receives the operational owner credential for reporting.

Proposed AWS demo network: two AZ public subnets for managed workers with public egress and no inbound internet rules, two private subnets for internal ALB/VPC link and RDS. Avoid NAT for this limited demonstration. Public worker addresses incur charges and require careful security groups; private-worker production topology needs costed NAT/endpoints. Private EKS API access for nodes plus restricted public API access for the operator. One worker is a cost minimum, not HA; two are needed for node-failure demonstration. Size from measured memory including Metabase and system pods, not wishful micro-instance capacity.

## Data and partial failure design (future)
Booking creation records a pending booking and price snapshot. Verified payment atomically confirms the booking and writes the purchase outbox event. Only a verified provider webhook may transition payment/booking to confirmed; unique provider event IDs and conditional state transitions prevent duplicate confirmation. Booking command idempotency key binds to user plus payload hash. Prices use integer cents; all event times UTC, reporting timezone configurable (initial assumption Asia/Colombo). Capacity/double-booking rules are unresolved; do not invent park capacity.

Planned transactional outbox publishers retry to SQS with bounded exponential backoff/jitter. Delivery is at least once; the worker inserts a unique event ID and projection updates in one transaction, deleting a queue message only after commit. DLQ handles poison messages. Booking remains usable during analytics failure; dashboards show projection lag. A DB outage remains a shared limitation. CQRS does not require implementing full event sourcing.

Gate verifies a signed ticket independently of a synchronous booking call, records a unique booking check-in and guest count transactionally, and uses locally projected revocation/confirmation state. Revocation freshness and fail-closed policy must be defined before implementation; signatures alone cannot detect refunds. Ride events require a valid checked-in booking, attraction, timestamp and guest count; do not bypass validation when a dependency fails. Catalog failure need not block an already priced booking. Payment outage leaves a pending booking; never invent a successful payment.

## Reporting model (future P4)
`reporting.events(event_id, event_type, occurred_at, booking_ref, tier_id, attraction_id, guest_count, amount_cents, currency)` contains minimized operational facts, no names or tokens. Arrival totals sum guest_count; purchased tickets count confirmed bookings grouped by snapshot tier; revenue sums confirmed amount_cents; popularity sums ride guest_count (also expose event count); hourly buckets include open hours with zero events for quiet periods. Define park opening hours, reporting timezone and refund policy before final SQL. Metabase reads stored facts with read-only role. Keep metadata separate and back it up or provision dashboards repeatably.

## Local versus cloud
Compose DNS provides local names, PostgreSQL volume persists development data, and optional Metabase connects locally. Compose is not a substitute for Minikube evidence. Worker is currently an inert skeleton, not a functioning pipeline. Terraform bootstrap/persistent and temporary demo resources have separate states; ordering is in architecture-decisions and roadmap. No Terraform implementation is included through Phase 2.

## Initial tier configuration for Phase 2
The assignment p2 prices are indicative; the user requests them as initial stored values: Individual exactly 1 guest / USD 40 (4000 cents), Couple exactly 2 / USD 75 (7500 cents), Family up to 4 / USD 140 (14000 cents), Group up to 5 / USD 165 (16500 cents). Minimum Family/Group count is provisionally 1 pending review; do not confuse tier capacity with actual arrival count. Prices belong in seeded database rows, editable by administrators, with a snapshot copied into each booking. Phase 2 seeds these rows non-destructively, reads them in the frontend and tests price snapshots; pricing management UI remains Phase 3.
