# AWS deployment and testing results

The `r20261016-tf-lifecycle7` rehearsal created 45 Terraform resources and built all six images and both websites on AWS. PostgreSQL and Metabase ran on the server; the Mac acted as the controller and private backup/state holder. This is a single-node Kubernetes demonstration, with no claim of multi-node or managed-database high availability.

## Observed results

| Check | Result |
|---|---|
| Automated regression checks | 198 passed, including 16 lifecycle guard tests |
| Complete infrastructure and server-side application release | Passed |
| Visitor/admin Amplify hosting, API Gateway, TLS and CORS | Passed |
| Real visitor signup, email confirmation and password login | Passed |
| Admin authorization and second visitor ownership isolation | Passed |
| Attraction create/update/retire and tier pricing revisions | Passed; original price restored and existing booking amount preserved |
| Concurrent booking creation | Four requests with one idempotency key produced one reference |
| Stripe sandbox Checkout | Successful card confirmed booking through the signed webhook |
| Declined sandbox card | Stripe displayed the decline; booking remained pending/unpaid |
| Payment retry | Re-signed replay of the observed sandbox event returned duplicate; the original delivery came from Stripe |
| Gate concurrency | One admission and three duplicate conflicts from four requests |
| Booking service outage | Gate independently admitted a valid signed ticket |
| Gate service outage | New pending booking succeeded |
| Ride retry | Duplicate event did not create another ride record |
| Analytics worker outage | Ride event persisted in outbox, then drained after worker restart |
| Pod replacement | New catalog pod became ready; all 31 public probes returned success |
| Green deployment and rollback | Alternate release metadata served; blue restored and green scaled to zero. Domain code/image were identical |
| Metabase | All seven stored SQL cards executed after business events |
| Reporting reconciliation | One paid booking, USD 140, four admitted guests, two ride events/eight riders; no pending outbox records |

Only [Stripe sandbox test cards](https://docs.stripe.com/testing) were used. No real payment funds moved.

## Interpretation of timing and load

This run occurred after the available booking slots. The system first rejected a future-date ticket at the gate. For the positive same-day gate test, maintenance SQL adjusted **only the paid disposable booking's visit date**, preserving its real sandbox payment, amount and payment status. The API then issued a fresh signed ticket. Production booking-date checks and AWS demo-mode settings remained enabled. Repeat the user demonstration during operating hours with a normal same-day booking; do not present this fixture as a normal same-day purchase after closing.

Reporting correctly records four arrivals outside operating hours. Operating-hour bars are zero and all hours tie for busiest/quietest; no meaningful business peak can be inferred from this small after-hours dataset. The two ride events for Little Explorers total eight riders.

A burst load triggered an observed HPA cycle from two to three ready replicas and back to two. That burst exceeded the configured gateway rate of 20 requests/second: 979 requests succeeded and 11,021 were unsuccessful; those unsuccessful responses were not individually classified. This is not a zero-error or capacity benchmark.

A separate test capped at 18 requests/second returned **2,724 HTTP 200 responses and zero errors**. CPU utilization stayed below the 70% HPA target (maximum sampled 53%), so retaining two replicas was expected. The test harness's demand for another scale-up did not pass; the observed low-load behavior was correct. Gateway limits were not raised for testing.

## Lifecycle and retained evidence

A fresh private database backup was taken before Terraform teardown and verified by SHA-256 and gzip validation. Restore from that backup has not been rehearsed. The first destroy pass hit an authorization error on a stale EIP association after server termination; a refreshed plan contained only the detached IP. The cleanup helper now retries once only after refreshed Terraform state confirms the approved remaining scope is limited to the demo EIP/association, AWS reports no active demo server, and the IP is detached. Attached IPs or other remaining resources stop the automatic retry. Four regression cases cover these guards; no IAM permission expansion was made. The refreshed detached-IP deletion was applied live; a new full deployment/destroy cycle after this helper change has not been repeated.

Cleanup status is recorded in [the machine-readable rehearsal results](evidence/aws-rehearsal.json).

Deployment IAM policy definitions and user attachments, local `.env`, source, configuration, Terraform state, private logs and backups remain for the next deployment. Disposable server IAM roles are recreated by Terraform. Cloud runtime secrets and the matching temporary Stripe webhook are removed along with the demo; new ones are created on the next deployment. Never publish `.env` or `secrets/`.

## Simple commands for the next demonstration

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./cloud.sh cleanup-check
./cloud.sh up
```

Review the real plan/cost and type `UP`. Wait for the full command to finish. `up` builds the images/websites on AWS and installs the application. It creates new hosted URLs, accounts and a Stripe test webhook. No laptop Docker or Node installation is required for these cloud commands.

```bash
./cloud.sh status
./cloud.sh verify
./cloud.sh monitoring
```

Open the URLs from `status`. Private demo credentials are in `secrets/simple-cloud/accounts.json`. Metabase is reached at http://127.0.0.1:3001 while `monitoring` remains running; its credentials are in `secrets/metabase-ec2.json`. `verify` checks the base platform and SQL cards; interactive payment and business-flow acceptance are separate checks described above.

Follow [the demonstration steps](../archive/aws-demo-notes.md#demonstration-rehearsal), booking a same-day visit during valid hours. Refresh Metabase after the purchase, gate admission and ride events, and explain every total.

When finished, stop the monitoring tunnel with Ctrl+C, then:

```bash
./cloud.sh down
./cloud.sh cleanup-check
```

Review the deletion plan, type `DOWN`, and keep the terminal open until deletion and inventory verification finish. Do not manually terminate EC2 first: doing so prevents a fresh database backup. A stopped server alone leaves storage/IP resources allocated. If cleanup fails, retain the error and retry `down` with a refreshed plan; never assume failure means everything is gone.

Remaining assignment work: user review of hosted pages and chart appearance, an operating-hours demonstration without the date fixture, authorized GitHub publication and observed remote CI, final report/screenshots/student details, and submission. The live checks do not claim the entire assignment is submitted or complete.
