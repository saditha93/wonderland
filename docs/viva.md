# Viva speaking guide

Use [demo.md](demo.md) for the exact sequence. Prepare the deployment before your presentation so image downloads do not consume speaking time. Show a real Terraform creation/cleanup when the examiner requests IaC evidence; an offline mock is labelled as such.

## A short presentation

**Opening — 30 seconds**

“Wonderland is a theme park booking MVP. Visitors browse, book, pay and receive signed tickets. Administrators manage attractions/prices, admit guests and record ride activity. Reporting uses actual events from those operations.”

**Architecture — 60 seconds**

Open `docs/diagrams/system.mmd` and the report. Explain four independently built services: attractions, booking/payment/profile, gate/rides and analytics. Each owns a PostgreSQL schema. Cognito authenticates users, API Gateway receives requests, and Kubernetes runs the workloads. Amplify hosts separate visitor and admin sites. Metabase reads reporting views through a read-only database role.

“The demo uses one 8 GiB EC2 server for Kubernetes, PostgreSQL and Metabase. This keeps the teaching deployment manageable. A whole-server or database outage remains a shared failure; I am not claiming multi-node high availability.”

**Infrastructure and commands — 60 seconds**

```bash
./demo.sh help
./demo.sh terraform-check
./demo.sh status
./demo.sh check
```

Explain that `terraform-check` uses mocked providers and creates no AWS resources. For a real deployment, `up` reviews/applies Terraform, then coordinates server builds and the application release. Splitting `.tf` files by purpose improves navigation while keeping one state and the same resource addresses.

Open `infrastructure/terraform/aws/network.tf`, `server.tf`, `identity.tf` and `gateway.tf`. Point to ownership tags, encrypted storage, restricted public ports and the gateway origin check. Explain that the separate permissions root sets up the deployment user's bounded IAM grants.

**Business demonstration — 3 minutes**

1. Show a valid visitor booking and its stored price. A retry uses the same idempotency key.
2. Complete a Stripe sandbox payment. The signed webhook must match the stored session, amount and currency before confirmation.
3. Show the reference and signed QR ticket. The gate verifies its signature and visit date using the public key.
4. Admit the party once, show duplicate rejection and record a ride.
5. Explain role/owner checks: hiding admin buttons alone does not protect the API.

Use a valid same-day booking during operating hours. The earlier after-hours fixture is disclosed in the results; it is not an ordinary purchase flow.

**Reporting and reliability — 90 seconds**

```bash
./demo.sh monitor
```

Refresh the seven dashboard cards and explain booking count, guests, revenue, rides and hourly activity. “The analytics worker drains an outbox through SQS. Event IDs prevent duplicate facts. A worker outage delays reporting; the source transaction and its event remain durable.”

Show the observed rehearsal results: one paid booking/USD 140, four admitted guests, two ride events/eight riders; worker catch-up and pod replacement passed. Explain the load evidence carefully: the burst induced 2→3→2 scaling with unsuccessful requests above the gateway limit; a separate 18 requests/second run returned 2,724 successes and zero errors while staying below the scaling threshold. These measurements describe the small demo, not production capacity.

**Close — 30 seconds**

```bash
./demo.sh down
./demo.sh audit
```

“Cleanup verifies a fresh database backup before destroying the approved stack, then checks for leftovers. Local state, backups and deployment permissions are retained for reuse. A stopped server can leave storage/IP allocated.”

## Questions to prepare

| Topic | Explain it simply |
|---|---|
| Why microservices? | Booking, admissions and reporting have different responsibilities. They can be built and tested independently. The shared host/database remains a demo trade-off. |
| Why separate schemas? | Each service owns its tables and database role. Other services use APIs/events rather than writing those tables. |
| Why Kubernetes? | Deployments maintain replicas, probes control readiness and the catalog HPA adjusts pods. Pod replacement was demonstrated. |
| Why an API gateway? | One API entry point provides routing, origin controls and bounded request throttling. |
| Why Cognito and API authorization? | Cognito proves identity. The backend separately checks administrator membership and record ownership. |
| Why is payment confirmation asynchronous? | The browser can close or retry. A verified provider webhook is the authoritative payment notification. |
| What is idempotency? | Repeating one logical request with the same key/event ID produces one booking, admission or reporting fact. Conflicting reuse is rejected. |
| Why a signed ticket? | Gate can validate the paid ticket independently while the booking API is unavailable. It still checks visit date and duplicate admission. |
| Why an outbox? | The business transaction stores its event in the same database transaction. A worker can retry delivery later. |
| How do reporting numbers stay correct? | Stable event IDs, payment matching and unique arrival/purchase keys prevent duplicate facts. Reconcile dashboard totals with source records. |
| Why Terraform? | Versioned infrastructure, reviewed plans, repeatable creation/deletion and traceable outputs. Scripts handle application build/release steps. |
| Why one server? | A small demonstration footprint fits the chosen budget and memory needs. Whole-host/DB failure remains a limitation. |
| Does HPA lower this EC2 bill? | It changes pod replicas. The fixed server, disk and public IP remain until the relevant infrastructure is removed. |
| Why retain IAM/state? | IAM defines reusable deployment permissions; private state tracks resources and supports safe cleanup. Neither is application source for the public ZIP. |
| What remains before submission? | Personal chart review, a normal-hours walkthrough, authorized GitHub publication and remote CI, final screenshots/student details and submission. |

## Know these code paths

- `scripts/aws/release.py`: the release sequence in one short function.
- `services/booking-service/app/reservations.py`: validation, price snapshot and idempotent creation.
- `services/booking-service/app/checkout.py`: verified confirmation and duplicate event handling.
- `services/booking-service/app/tickets.py` and `wonderland_common/tickets.py`: signing and verification.
- `services/analytics-worker/app/pipeline.py`: durable event processing and reporting.
- `scripts/aws/cleanup.py`: backup, reviewed deletion, guarded detached-IP recovery and audit.

See [code-guide.md](code-guide.md) for the complete map. Explain the reasoning in your own words and acknowledge assistance as required by the assignment.
