# Assignment coverage and completion gates

Reviewed 15 October 2026 against all four pages of the supplied SE6020 assignment. This is the current assessment checklist, not a claim that deployment or submission has finished. The source PDF SHA-256 is `8d91c2588dc4c25db389f895a08841632f4ec810a11073b978c8a84b9c722f37`.

## All marked areas

| Marked area | Weight | Project coverage | Evidence still required |
|---|---:|---|---|
| Solution report | 15% | `project-report.md`, architecture/design-pattern documents, requirements matrix and evidence register | Align final report with the topology actually deployed; add actual cloud screenshots/results, repository and hosted links, student details and acknowledgements; personally review/explain the work |
| Microservices | 20% | Independently containerized attractions, booking/payment/profile, gate/ride and analytics services; real PostgreSQL schemas; validation, authorization, signatures, retries and outbox | Exercise their integrated cloud business flow and service-failure behavior; retain results |
| Kubernetes with API Gateway | 20% | Actual local Kubernetes evidence; selected AWS plan runs K3s with Deployments, Service DNS, probes, replicas, persistent storage and catalog HPA, behind AWS API Gateway and verified HTTPS | Verify cloud gateway routing and readiness; demonstrate pod replacement, HPA scale-up/down, concurrent booking/check-in and analytics recovery under bounded load |
| Web interface, Amplify and Cognito | 15% | Separate React visitor/admin apps, two Amplify targets, Cognito signup/confirmation/login SDK flows, role and ownership checks | New visitor signs up with a real email and confirms it; both hosted portals work; a visitor cannot use admin APIs or another visitor's records |
| Monitoring dashboard and visualization | 10% | Timestamped purchase/arrival/ride facts; private Metabase with seven stored SQL cards and a read-only BI role | Query the cloud database, review chart appearance and reconcile every required metric with actual cloud demonstration records |
| Infrastructure as Code | 10% | Selected simple Terraform root plus automated bootstrap, migration, workload/image/hosting release commands; saved-plan/source checks; optional EKS/RDS roots retained | Run the selected stack and application release in a timed cloud rehearsal; record outputs, lifecycle/cost evidence and retained resources; repeat the commands in the viva |
| Integration demonstration | 10% | GitHub remote/workflow and source-only handover; remote SSH access verified | Commit/publish the intended reviewed source through the authorized Git workflow, retain a successful remote Actions run, verify examiner access and rehearse the entire flow |
| **Total** | **100%** | **Every rubric area has an implementation path** | **Live and manual evidence remains open; no marks or 100% completion claimed** |

## Functional acceptance: pages 1–3

All these features have implementation/local evidence. Each must also be demonstrated through the deployed environment where applicable.

| Requirement | What to show |
|---|---|
| Visitor and administrator profiles; secure registration/login | Cognito visitor signup, email confirmation and login; administrator group assignment; profile access; sign out |
| Browse rides and activities | Descriptions, category, thrill level and age/height suitability; include open and retired/maintenance behavior |
| Four tiers and one tier per booking | Individual 1/USD40, Couple 2/USD75, Family up to4/USD140, Group up to5/USD165 as initial indicative prices; reject excess guests and multiple-tier payloads |
| Date and preferred time slot | Accept an available date/slot; reject past dates and elapsed cloud slots; preserve Asia/Colombo date handling |
| Secure provider payment | Real Stripe sandbox Checkout, delivered signed webhook, stored amount/currency checks and duplicate event safety; failed/unpaid checkout must not produce a paid ticket |
| Digital ticket | Paid booking reference and signed QR; reject a tampered ticket |
| Booking and visit history | Correct owner's booking, arrival and ride history; deny another visitor access |
| Attraction administration | Create, update and retire an attraction through the admin portal; visitor mutation receives 403; retirement preserves history |
| Tier and pricing administration | Database-backed view/update of tiers/prices; old bookings retain their purchased price; new bookings use the new price |
| Arrivals/check-ins | Full party guest count, timestamp, correct date, paid-ticket check and duplicate admission rejection |
| Purchases and revenue by tier | Show actual purchased ticket counts and confirmed revenue separately; pending bookings contribute no revenue |
| Popular rides and activities | Record a timestamped ride for checked-in guests, enforce party bounds, show guest-weighted usage |
| Peak and quiet periods | Show hourly buckets, zero-activity hours and the configured timezone; distinguish arrivals from ticket purchases |

The assignment makes adult/child rates, peak pricing and seasonal promotions optional. Refunds, cancellation, partial-party admission and MFA are not explicit mandatory features. Their absence must not be described as a missing required feature.

## Monitoring acceptance: all required questions

Use the real deployed data, with Metabase's separate read-only `wonderland_bi` login. Metabase's own metadata uses separate ownership. The seven existing cards must all query successfully; the following required answers must be visible:

- Visitors arriving on a given day: sum admitted guests, not number of bookings.
- Purchased tickets by tier and revenue by tier: confirmed purchases and immutable price snapshots.
- Most popular rides/activities: recorded ride guest counts and stable attraction IDs.
- Busiest and quiet periods: actual timestamped activity, zero-filled operating hours and Asia/Colombo boundaries.

Capture a small source-to-dashboard reconciliation after the real sandbox payment, gate admission and ride event. A successful empty dashboard query is not proof that the complete event pipeline works. The dashboard stays private through SSM; public access is not required for assessment.

## Non-functional acceptance: page 3

| Attribute | Existing design and evidence | Required live proof and limit |
|---|---|---|
| Scalability | Stateless replicas, bounded database pools, catalog CPU HPA, SQS buffering, idempotency/concurrent transaction tests; recorded local HPA 2→3→2 and load evidence | Repeat bounded scaling and concurrent booking/check-in checks in AWS. Test ride-event bursts and drain/reconciliation. A catalog-only HPA does not prove booking/gate capacity or node autoscaling. Do not claim unmeasured production peak capacity |
| Security | Cognito token verification; admin/owner checks; Stripe signature and amount validation; restricted DB roles; RSA tickets; protected logs; encrypted EBS/S3/SQS; verified API/service/DB TLS; bounded IAM server role | Inspect deployed encryption; verify trusted TLS and direct-origin denial; test invalid/expired tokens, visitor admin denial and cross-user ownership. Confirm AWS/payment keys are absent from browser bundles and logs. Node role is shared within one trust domain, not per-pod IRSA |
| Fault tolerance | Independent signed-ticket verification at gate, outbox/deduplication, retries, circuit breakers, probes and pod replacement; actual local worker/database recovery tests | Interrupt one service at a time: gate outage must not prevent booking; booking API outage must not prevent valid signed-ticket gate admission; analytics outage must not block business writes and must catch up afterward. Catalog failure must degrade ride lookup safely. Database or whole-host failure affects this single-node design; do not claim multi-node/DB high availability |
| Cost efficiency | Small ARM server; bounded catalog HPA; managed hosting/identity/queue; six-hour server stop timer; explicit stop/start commands; Free-plan checks | Show runtime/credit usage and stop behavior. Inventory disk, fixed IPv4, hosting/storage/log/secret usage that remains after stop. Pod HPA alone does not reduce an EC2 bill. No paid-plan upgrade or purchased domain is authorized |

## Infrastructure interpretation

- Page 4 Task 6 says Kubernetes and gives EKS/GKE as examples. K3s is the selected Kubernetes implementation; the API Gateway requirement also appears explicitly in the marks table. Merely showing Docker Compose would leave this assessed area uncovered.
- Page 1 suggests RDS, DynamoDB or an equivalent managed database; page 4 Task 7 says to use a database. The selected PostgreSQL StatefulSet provides persistence on encrypted EBS. It is **self-managed**, so do not label it RDS or a managed database. The optional EKS/RDS design remains available if the lecturer expects managed infrastructure beyond the task wording.
- Page 4 Task 8 explicitly accepts CloudFormation or Terraform. Page 3 uses cloud-specific CloudFormation/Terraform examples. The submission should explain its Terraform-on-AWS choice against Task 8; do not silently claim that CloudFormation was implemented.
- The live IaC demonstration comprises Terraform provisioning **and** the scripted application release/migration/hosting. Showing a pre-existing server or an offline mock plan alone is insufficient.
- The simple deployment uses local private Terraform state. Back it up securely; it must not go into the node-readable public-code artifact bundle. Explain this demo trade-off separately from the optional remote-state design.

## Final completion gates

Do not label the AWS assignment demonstration complete until each gate has observed evidence:

- [ ] Reviewed permissions installed; actual Free-plan provisioning accepted without upgrade.
- [ ] IaC and scripted release create the complete selected cloud infrastructure/workloads/hosting; actual HTTPS gateway works.
- [ ] Hosted visitor signup/email confirmation and visitor/admin login pass; owner and role isolation pass.
- [ ] Real Stripe sandbox checkout/webhook confirms the stored purchase exactly once; failed payment remains unpaid.
- [ ] Signed ticket, same-day gate admission, duplicate rejection, ride recording and owned histories pass during valid park hours.
- [ ] All seven cloud Metabase cards query; arrivals, purchases/revenue, rides and hourly activity reconcile with source records.
- [ ] Cloud bounded scaling, concurrent operations, pod self-heal and service/outbox recovery are demonstrated; limitations documented.
- [ ] Reviewed source is on the submitted real GitHub repository; an observed successful CI run and examiner-accessible links exist.
- [ ] Report/diagrams describe the actual topology and observed results; screenshots, references and required help acknowledgements are included.
- [ ] Timed viva rehearsal includes live IaC/release, full business flow, failure/scale evidence and stop/residual-cost explanation.
- [ ] Student verifies current Moodle deadline/submission status and submits the report plus code/artifact links. The supplied PDF lists 11 October 2026 for submission and 8 November 2026 for viva; no extension is assumed here.

Current evidence: [small-cloud preflight](evidence/simple-cloud-preflight.json), [recorded local validation](validation.md), [local infrastructure results](evidence/local-infrastructure.json). Commands: [small AWS demonstration guide](simple-aws-demo.md). Detailed requirement IDs: [traceability matrix](requirements-matrix.md).
