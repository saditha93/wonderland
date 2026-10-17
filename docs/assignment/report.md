# Wonderland: booking, admission and reporting MVP

SE6020 — Cloud Computing / Architecting Enterprise Cloud Solutions
Student name: **[complete]** · Student ID: **[complete]**
Repository/submission links: **[complete after authorized publication]**

**Evidence status:** the reorganized release `r20261017-tf-lifecycle8` was deployed and rehearsed on 17 October 2026. Local checks pass 200 regression tests, both frontend builds, startup/shutdown and six offline Terraform configurations. Browser testing found and corrected an OPTIONS preflight failure; hosted visitor/admin login and reports then passed. Personal chart review, an ordinary operating-hours walkthrough, remote CI and submission remain open. See the results guide for final cleanup status.

## 1. Objective and scope

Wonderland supports visitors browsing attractions, registering/signing in, booking one ticket tier for a party/date/time, paying in a Stripe sandbox, obtaining a signed QR ticket and viewing owned history. Administrators manage attractions and pricing, admit paid bookings, record ride activity and inspect operational reports. The requirement map and checklist below map the supplied assignment to implementation and evidence.

There are separate React visitor and administrator entry points. The API enforces identity, role and ownership checks regardless of which website sends a request. Refunds, partial arrival, re-entry and production capacity planning are outside this MVP.

## 2. Implemented architecture

The selected AWS topology uses Amplify for the two websites, Cognito for managed identity and API Gateway for the HTTP API. API Gateway sends requests over verified HTTPS to an origin-protected NGINX proxy on one 8 GiB EC2 server. K3s runs the service workloads, PostgreSQL and Metabase. ECR stores immutable images, S3 holds private build artifacts, SQS transports events and CloudWatch receives application logs. The current [system diagram](../diagrams/system.mmd) shows this topology.

Four independently built services separate attractions, booking/payment/profile, gate/rides and analytics. PostgreSQL schemas and database roles separate ownership. This is self-managed PostgreSQL on encrypted EBS, not RDS. The optional EKS/RDS design is retained under `infrastructure/terraform/advanced/`; it is not the topology used for the core cloud rehearsal.

One server keeps the small demonstration manageable and within its reviewed memory/budget needs. A server or database outage is a shared failure domain. Pod replicas and HPA do not establish multi-node high availability or lower a fixed EC2 bill automatically.

## 3. Booking, payment and ticket integrity

Reservation creation validates the tier, party size, visit date and future time slot. It stores the tier name, revision and price at creation. Subsequent administrative price changes do not rewrite an existing booking's amount. An owner/idempotency-key constraint makes a retry return the existing logical booking; conflicting reuse is rejected.

Stripe Checkout is sandbox-only. The booking remains pending until a webhook signature is verified and its session, reference, amount and currency match stored data. Event IDs/fingerprints deduplicate notification retries. The confirmation transaction updates payment state and stores a purchase event in the outbox. A declined payment remains unpaid and produces no reporting revenue.

Only confirmed bookings receive signed RS256 QR tickets. The gate verifies the public key, audience, issuer, ticket kind and visit date independently of the booking API. A unique check-in constraint admits the full booked party once. Ride records require admission, a valid visit date, an open attraction and a permitted guest count; event IDs deduplicate retries.

## 4. Reporting and resilience

Business transactions retain events in an outbox. The analytics worker publishes/consumes queued events and records each processed event ID before creating reporting facts. A worker outage delays reports while business events remain durable. The reporting schema separates purchases, arrivals and rides. Metabase uses a read-only BI login and seven saved SQL cards for daily arrivals, tickets/revenue by tier, attraction popularity, hourly arrivals, busiest/quietest hours and outside-hours arrivals.

Kubernetes startup/readiness/liveness probes, replicas and replacement improve process recovery. Circuit breakers and bounded operations limit dependency failures. The catalog HPA uses CPU utilization within a two-to-three replica bound. A whole-host or shared-database failure still requires operational recovery; it is not covered by independent pod replicas.

## 5. Infrastructure, security and lifecycle

The main Terraform root is `infrastructure/terraform/aws/`. Files are split by network, compute, storage, identity, hosting, gateway and monitoring while retaining resource addresses and one private local state. Terraform versions/providers are pinned. The separate `permissions/` root manages reusable bounded deployment grants; normal demo cleanup retains those policy definitions and attachments.

`./demo.sh up` reviews the actual target/plan/cost, then provisions resources and coordinates application release. Server-side helpers build images and both websites, run migrations, configure Kubernetes and publish Amplify artifacts. Static AWS keys do not enter public source bundles or server build commands. Runtime material is fetched privately through Secrets Manager; temporary build credentials are removed from the current runtime value after use.

Cognito JWTs establish identity; the services enforce administrator membership and ownership. Service/database TLS, encrypted disk, a private artifact bucket, protected origin routing, limited public ports, restricted runtime permissions and private Metabase access define the security boundaries. The server role is one shared trust domain; per-pod IRSA is not claimed for this topology.

`./demo.sh down` verifies a fresh off-server database backup before reviewed Terraform deletion and then audits remaining resources. A bounded retry handles only a detached demo IP after no active demo server remains. Other leftovers, associated IPs or backup failures stop the automatic path. Local state, configuration, evidence and backups remain private. Backup checksum/gzip validation passed; restore has not been rehearsed.

## 6. Observed results and limits

The reorganized AWS rehearsal provisioned 45 resources and completed server-side container/site builds, HTTPS routing, Cognito confirmation/login, role/owner checks, successful and declined sandbox payments, payment retry handling, concurrent admission, ride retry handling, booking/gate isolation, analytics recovery, pod replacement and seven Metabase SQL queries. Source and reporting records reconciled to one paid booking/USD 140, four admitted guests and two ride events/eight riders.

The run occurred after available booking slots. It first rejected a future-date gate ticket, then used a documented one-booking visit-date fixture for the positive same-day admission test. Application date checks remained enabled. This does not prove an ordinary same-day purchase after closing. Hourly reports correctly showed outside-hours arrivals and zero operating-hour counts; the small dataset does not establish a meaningful business peak.

A burst triggered an observed HPA 2→3→2 cycle, with 979 successes and 11,021 unclassified unsuccessful responses above the gateway's configured 20 requests/second limit. A separate 18 requests/second test returned 2,724 successes and zero errors; CPU stayed below the HPA threshold and two replicas were retained. These are bounded demo observations, not a production capacity benchmark.

The reorganized release completed the full Terraform lifecycle. The initial destroy encountered the known stale IP-association error; its bounded automatic retry refreshed state and released only the detached demo IP. No IAM expansion was needed. A fresh database backup was verified before deletion; Terraform state ended with zero resources. Final inventory and backup details are recorded in the results guide.

Detailed observations: [AWS results](../results/aws-rehearsal.md), [machine-readable evidence](../results/evidence/aws-rehearsal.json), and [current commands](../demo.md).

## 7. Submission and handover

`./demo.sh package` creates a source-only ZIP with hashes, excluding credentials, private databases/state, installed dependencies and generated builds. This is a bounded packaging safeguard. The CI workflow runs local regression/build/container checks and offline Terraform validation without AWS credentials; a successful remote workflow must be observed after authorized publication.

The student must review the hosted pages/dashboard, rehearse the ordinary operating-hours flow, add screenshots and personal details, verify repository access, observe CI and submit through the required process. [The viva guide](../viva.md) supports an explanation in the student's own words.

## 8. References and acknowledgement

[1] SLIIT, *Assignment — Cloud Computing 2026 — AUG*, supplied course document, pp1–4. Primary functional requirements, tasks and assessment weights. Original retained privately.

[2] SLIIT, *Lecture 4 — Cloud Design Patterns*, supplied slides: CQRS pp8–14; discovery pp21–22; circuit breaker pp23–24; gateway pp25–27; health checks pp36–37. Pattern selections are explained in [the code guide](../code-guide.md#design-choices).

[3] SLIIT, *Lab 5 — Introduction to Docker*, supplied practical material. Supporting containerization context.

[4] SLIIT, *Lab 7 — Stepping into K8s*, supplied practical material. Supporting Kubernetes workload/service context.

[5] SLIIT, *Lab 8 — K8s Deep Dive*, supplied practical material. Supporting orchestration/recovery context.

[6] SLIIT, *SE6020 module outline*, supplied course document. Learning outcome and individual assessment context.

Implementation evidence: [code and design guide](../code-guide.md), [local demonstration commands](../demo.md#optional-laptop-demonstration), [AWS deployment guide](../deployment.md) and [recorded AWS results](../results/aws-rehearsal.md). The optional [optional EKS design](../deployment.md#optional-eksrds-design) describes a separate design that was checked offline.

OpenAI Codex assisted implementation, testing and drafting. The student must personally review the report, understand and explain the code, verify the lecturer's acknowledgement policy, add required personal/submission details and acknowledge other help accurately. No assistance acknowledgement or machine-generated report substitutes for individual understanding or submission approval.

## Assignment checklist

The seven marked areas below separate recorded evidence from the student’s remaining work. Detailed outcomes are in [AWS results](../results/aws-rehearsal.md).

| Area | Weight | Implementation and recorded evidence | Still to do |
|---|---:|---|---|
| Solution report | 15% | Report, system diagram, design choices and observed limitations | Add student details, screenshots, final links and personal review |
| Microservices | 20% | Four containerized services; bookings, payments, admission, rides and reporting exercised in AWS | Repeat the ordinary visitor journey with the student |
| Kubernetes and API Gateway | 20% | K3s, HTTPS gateway, probes, pod replacement and bounded HPA/recovery checks | Explain the single-host limit; full HPA scale-up/down was recorded in the earlier run |
| Web, Amplify and Cognito | 15% | Separate hosted apps, confirmed email/signup/login, role and owner checks | Review hosted screen appearance and usability |
| Monitoring and visualization | 10% | Seven Metabase SQL cards queried and reconciled with purchases, arrivals and rides | Review chart appearance and capture screenshots |
| Infrastructure as Code | 10% | Terraform provisioned 45 resources; scripted release, backup and teardown observed | Review the latest recorded lifecycle and rehearse the commands personally |
| Integration demonstration | 10% | Local regression/build checks and source-only handover | Publish reviewed source, observe remote CI, verify examiner access and rehearse the timed viva |

## Before submission

- [ ] Complete a purchase → payment → ticket → admission → ride → reporting walkthrough during valid booking hours. The previous positive gate test used a documented after-hours date fixture.
- [ ] Review visitor/admin pages and every Metabase chart; capture useful screenshots without passwords or tokens.
- [x] Deploy and test the reorganized release, retaining its own results and documented proxy correction.
- [x] Observe Terraform creation, application release, verified backup and cleanup; state ended empty. Repeat the timed command demonstration personally for the viva.
- [ ] Add student details, repository/hosted links, references and required assistance acknowledgements to the report.
- [ ] Verify successful remote CI and examiner access to the submitted source.
- [ ] Explain the code and architecture personally using the [viva guide](../viva.md).
- [ ] Verify the current Moodle deadline and submit the report plus source/artifact links. The supplied assignment lists 11 October 2026 for submission and 8 November 2026 for viva; no extension is assumed.

## Infrastructure interpretation

K3s supplies Kubernetes on the selected server; it is not EKS. PostgreSQL on encrypted EBS is self-managed, not RDS. The assignment's database guidance mentions managed options; confirm with the lecturer if a managed database is expected. The optional EKS/RDS files remain available. Terraform is explicitly accepted in Task 8. Pod HPA changes replicas, not the fixed EC2 bill, and one server does not provide multi-node high availability.

Primary assignment PDF SHA-256: `8d91c2588dc4c25db389f895a08841632f4ec810a11073b978c8a84b9c722f37`. Original teaching materials remain private under `docs/course-materials/`.

## Assignment requirements

Source: supplied SE6020 assignment, pages 1–4. This map points to the current implementation. [Coverage](#assignment-checklist) lists remaining submission work; [recorded AWS results](../results/aws-rehearsal.md) distinguish observed behavior from limitations.

## Functional requirements

| ID | Requirement | Implementation | Demonstrate |
|---|---|---|---|
| F01 | Secure visitor/admin identity and profiles | Cognito, `wonderland_common/auth.py`, booking `profiles.py`, frontend `auth/` | Confirm email, sign in, deny visitor admin access |
| F02 | Browse attraction details and suitability | Attractions service and visitor `AttractionCard.tsx` | Show description, category, age/height and availability |
| F03 | One tier, valid party size, date and slot | Booking `reservations.py` | Reject excess guests, past dates and elapsed cloud slots |
| F04 | Secure payment | Booking `checkout.py` and `payments.py` | Stripe sandbox success/decline; signed, deduplicated webhook |
| F05 | Digital reference and QR ticket | Booking `tickets.py`, shared ticket signing/verification | Paid ticket works; tampered ticket fails |
| F06 | Own booking and visit history | Booking store/profiles, gate history, visitor `AccountPanel.tsx` | Owner sees records; another visitor is denied |
| F07 | Admin attraction create/update/retire | Attractions routes and admin `AdminPanel.tsx` | Update availability; preserve historical references |
| F08 | Stored, editable tiers and prices | Booking `pricing.py` and reservation price snapshots | New price affects new bookings; old purchase stays unchanged |
| F09 | Timestamped gate arrivals | Gate/ride service and unique check-in constraint | Admit the full party once on its visit date |
| F10 | Tickets sold and revenue by tier | Reporting purchase facts and SQL queries | Count confirmed purchases; exclude unpaid bookings |
| F11 | Popular attractions | Ride events and guest-weighted reporting | Record valid riders; retry produces no duplicate fact |
| F12 | Busiest and quiet periods | Zero-filled hourly SQL queries in Asia/Colombo | Explain opening hours and outside-hours arrivals |
| F13 | Durable arrival, purchase and ride data | Service outboxes, SQS and analytics worker | Pause worker, create events, resume and reconcile |
| F14 | Stored-data visualization | Metabase dashboard, seven SQL cards, read-only BI role | Match chart totals to the underlying demonstration records |

Initial tiers are Individual (1 guest/USD40), Couple (2/USD75), Family (up to 4/USD140) and Group (up to 5/USD165). Adult/child rates, peak pricing and seasonal promotions are optional. Refunds, cancellation, partial arrival and re-entry are outside this MVP.

## Quality requirements

| ID | Requirement | Implementation and limits |
|---|---|---|
| N01 | Scalability and concurrency | Stateless replicas, bounded pools, catalog HPA, SQS, idempotency and transaction constraints. Recorded burst failures are not a production capacity result. |
| N02 | Authentication and data protection | Cognito verification, admin/owner checks, restricted database roles, signed tickets, validated webhooks and redacted logs. |
| N03 | Encrypted storage and communication | Encrypted EBS/S3/SQS and verified HTTPS/service/database TLS. Runtime credentials remain private. |
| N04 | Resilience and failure isolation | Independent gate ticket verification, outbox retries, circuit breakers and readiness probes. Shared host/database failure remains a limitation. |
| N05 | Cost control | Reviewed plans, eligible server checks, stop timer, backup-before-destroy and residual-resource audit. Pod scaling does not reduce the fixed server charge. |

## Deliverables

| ID | Assignment task | Project location / evidence |
|---|---|---|
| D01 | Solution report and design | [Report](report.md), `docs/diagrams/system.mmd`, [design choices](../code-guide.md#design-choices) |
| D02 | Microservices | `services/`, shared `wonderland_common/`, regression tests |
| D03 | Web, Amplify and Cognito | `frontend/src/{visitor,admin,auth,shared}/`, Terraform hosting/identity |
| D04 | Container images | Service Dockerfiles; server image builder and ECR |
| D05 | Kubernetes and API Gateway | K3s workloads and Terraform gateway; optional EKS design retained separately |
| D06 | Database persistence | PostgreSQL schemas/migrations and encrypted server storage; self-managed rather than RDS |
| D07 | Run Infrastructure as Code | `infrastructure/terraform/aws/`, `./demo.sh up`, `down`, `audit`; [deployment guide](../deployment.md) |
| D08 | Repository integration | `.github/workflows/ci.yml`; successful remote CI and examiner access still need verification |
| A01 | Submission and viva | Source-only ZIP, report, [demo](../demo.md) and [viva guide](../viva.md); final submission is the student's responsibility |
| A02 | Individual understanding and acknowledgements | Personally review the implementation, references and assistance disclosure in the report |

The marked weights and final manual gates are maintained once in [the assignment checklist](#assignment-checklist).
