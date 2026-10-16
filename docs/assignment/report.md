# Wonderland: booking, admission and reporting MVP

SE6020 — Cloud Computing / Architecting Enterprise Cloud Solutions
Student name: **[complete]** · Student ID: **[complete]**
Repository/submission links: **[complete after authorized publication]**

**Evidence status:** the original AWS implementation completed a core cloud rehearsal. The source has since been reorganized and verified with 198 regression tests, both frontend builds, local startup and six offline Terraform configurations. A new complete AWS run of the reorganized source is not claimed. UI/chart review, an ordinary operating-hours walkthrough, remote CI and submission remain open gates.

## 1. Objective and scope

Wonderland supports visitors browsing attractions, registering/signing in, booking one ticket tier for a party/date/time, paying in a Stripe sandbox, obtaining a signed QR ticket and viewing owned history. Administrators manage attractions and pricing, admit paid bookings, record ride activity and inspect operational reports. [Requirements](requirements.md) and [coverage](coverage.md) map the supplied assignment to implementation and evidence.

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

The original AWS rehearsal provisioned 45 resources and completed server-side container/site builds, HTTPS routing, Cognito confirmation/login, role/owner checks, successful and declined sandbox payments, payment retry handling, concurrent admission, ride retry handling, booking/gate isolation, analytics recovery, pod replacement and seven Metabase SQL queries. Source and reporting records reconciled to one paid booking/USD 140, four admitted guests and two ride events/eight riders.

The run occurred after available booking slots. It first rejected a future-date gate ticket, then used a documented one-booking visit-date fixture for the positive same-day admission test. Application date checks remained enabled. This does not prove an ordinary same-day purchase after closing. Hourly reports correctly showed outside-hours arrivals and zero operating-hour counts; the small dataset does not establish a meaningful business peak.

A burst triggered an observed HPA 2→3→2 cycle, with 979 successes and 11,021 unclassified unsuccessful responses above the gateway's configured 20 requests/second limit. A separate 18 requests/second test returned 2,724 successes and zero errors; CPU stayed below the HPA threshold and two replicas were retained. These are bounded demo observations, not a production capacity benchmark.

The first teardown pass encountered a stale IP-association authorization error. A refreshed Terraform plan released the detached IP, and inventory confirmed no active demo resources. The guarded automatic retry added afterward has four regression cases; another full AWS create/destroy cycle after the helper change and source reorganization has not been repeated.

Detailed observations: [AWS results](../results/aws-rehearsal.md), [machine-readable evidence](../results/evidence/aws-rehearsal.json), and [current commands](../demo.md). Historical local results remain separate under `docs/results/`; the earlier local report is retained under `docs/archive/`.

## 7. Submission and handover

`./demo.sh package` creates a source-only ZIP with hashes, excluding credentials, private databases/state, installed dependencies and generated builds. This is a bounded packaging safeguard. The CI workflow runs local regression/build/container checks and offline Terraform validation without AWS credentials; a successful remote workflow must be observed after authorized publication.

The student must review the hosted pages/dashboard, rehearse the ordinary operating-hours flow, add screenshots and personal details, verify repository access, observe CI and submit through the required process. [The viva guide](../viva.md) supports an explanation in the student's own words.

## 8. References and acknowledgement

[1] SLIIT, *Assignment — Cloud Computing 2026 — AUG*, supplied course document, pp1–4. Primary functional requirements, tasks and assessment weights. Original retained privately.

[2] SLIIT, *Lecture 4 — Cloud Design Patterns*, supplied slides: CQRS pp8–14; discovery pp21–22; circuit breaker pp23–24; gateway pp25–27; health checks pp36–37. Pattern selections are explained in [design patterns](../architecture/patterns.md).

[3] SLIIT, *Lab 5 — Introduction to Docker*, supplied practical material. Supporting containerization context.

[4] SLIIT, *Lab 7 — Stepping into K8s*, supplied practical material. Supporting Kubernetes workload/service context.

[5] SLIIT, *Lab 8 — K8s Deep Dive*, supplied practical material. Supporting orchestration/recovery context.

[6] SLIIT, *SE6020 module outline*, supplied course document. Learning outcome and individual assessment context.

Implementation evidence: [source/test guide](../local/testing.md), [architecture decisions](../architecture/decisions.md), [local infrastructure commands](../local/kubernetes.md), [cloud runbook and its primary technical references](../advanced/eks-runbook.md), and the timestamped local evidence record.

OpenAI Codex assisted implementation, testing and drafting. The student must personally review the report, understand and explain the code, verify the lecturer's acknowledgement policy, add required personal/submission details and acknowledge other help accurately. No assistance acknowledgement or machine-generated report substitutes for individual understanding or submission approval.
