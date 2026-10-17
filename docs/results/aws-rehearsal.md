# Setup, testing and cleanup results

Rehearsal: **17 October 2026**, release `r20261017-tf-lifecycle8`, AWS account `459154641936`, `us-east-1`. The reorganized application was built on AWS and tested against its new hosted URLs. [Machine-readable results](evidence/aws-rehearsal.json) contain the observed checks and final cleanup status.

| Area | Observed result |
|---|---|
| Regression | 200 tests passed; both visitor/admin production builds passed |
| Terraform | All six roots validate and mock-test; real plan created 45 demo resources |
| Laptop startup/stop | Readiness checks passed for four APIs and both frontends; processes stopped |
| Local business flow | Catalog, booking retry, simulated payment, signed ticket, gate/ride and persisted reports passed |
| Cloud release | Six ECR images, two Amplify websites, Kubernetes workloads, migrations, PostgreSQL and Metabase passed |
| Security | Cognito roles, owner restrictions, unauthenticated denial, trusted TLS and direct-origin denial passed |
| Hosted browser | Visitor/admin login, booking history, administrator dashboard and report tables passed after preflight fix |
| Stripe sandbox | Successful checkout confirmed through its signed webhook; declined card remained pending/unpaid; duplicate event replay detected |
| Administration | Attraction create/update/retire; visitor mutation denied; pricing revision and immutable booking amount passed; original price restored |
| Concurrent operations | Four booking requests returned one reference; gate returned one 201 and three 409 conflicts |
| Isolation | Gate admitted a signed paid ticket while booking was stopped; a new booking succeeded while gate was stopped |
| Recovery | Replacement catalog pod became ready while public probes succeeded; worker outage retained ride event and drained after restart |
| Reporting | One paid booking/USD140, four admitted guests and two rides/eight riders reconciled; source outboxes drained |
| Metabase | All seven stored SQL cards executed through the private SSM tunnel after business activity |
| Bounded load | 2,724 HTTP 200 responses; zero failures at 18 requests/second; HPA returned/remained at two replicas |
| Backup | Fresh off-server backup verified by SHA-256/gzip; contains the paid test booking; restore not rehearsed |
| Teardown | Passed: down exited 0, detached-IP retry succeeded, state has zero resources, independent final audit found no active demo resources |

## Latest Minikube rehearsal — 17 October 2026

Release `r20261017-minikube3` was deployed on the 8 GiB EC2 server using Minikube v1.39.0, Kubernetes v1.36.5, kubectl and the built-in Ingress/metrics-server add-ons. No Helm or Traefik installation is used. The earlier table describes the K3s baseline; the results here describe the new live runtime.

| Check | New live result |
|---|---|
| Regression and IaC | 212 Python tests; visitor/admin builds; all six Terraform roots validate and mock-test |
| Real infrastructure | 45 AWS resources created; six ECR images published; separate Amplify apps released |
| Server access | Laptop SSH with the existing `sliit_test` key and restricted port 22 passed |
| Ingress | Four routes healthy through API Gateway; direct origin denied; HTTPS backend CA/name verification retained |
| Managed login | Visitor/admin Cognito login and backend authorization passed; browser login, history, dashboard and reports passed |
| Payment | Real Stripe sandbox decline stayed pending/unpaid; successful USD140 checkout confirmed through signed webhook; duplicate replay detected |
| Booking/gate | Four booking retries → one reference; gate concurrency → one 201 and three 409 responses; visitor gate mutation and invalid tickets denied |
| Independent services | Gate admission succeeded while booking was stopped; new booking succeeded while gate was stopped |
| Recovery | Replacement catalog pod became ready while public probes stayed successful; durable ride event drained after analytics worker restart |
| Reporting | One paid purchase/USD140, four admitted guests, two rides/eight riders; source and reporting totals reconcile with no pending outbox events |
| Monitoring | All seven stored Metabase SQL cards queried through SSM; CloudWatch received application logs |
| Bounded public load | 2,724 HTTP200 responses, zero errors, 18 requests/second; HPA metrics healthy and two-replica baseline retained |
| Restart | Minikube, all application pods, routing and private Metabase forwarding recovered; paid booking/reporting survived; full platform check passed again |

The new paid booking used a valid same-day future slot during opening hours. No database date fixture was used. This load did not trigger scale-up, so it is not evidence of a new 2→3→2 cycle. Email signup/confirmation was not repeated. GitHub publication/remote CI and optional EKS/RDS remain outside this rehearsal.

Two issues were found and fixed: CPU requests left Metabase pending with Minikube's control-plane reservation, so the demo renderer now leaves scheduling headroom; and backend failure after Cognito login left a partial session, so failed session acceptance now clears managed tokens. The outage/retry browser test passed. A startup `wonderland-routing` service restores private TLS/Ingress settings after Minikube reapplies add-on defaults. The final runtime fix was installed on the server and exercised after restart; backup restore into a separate database was not rehearsed.

Terraform teardown completed after resuming an interrupted deletion. State has zero managed resources. The full AWS inventory found only the detached public IP; its final independent EC2 query is now empty. A fresh SHA-256/gzip-verified backup contains the paid booking. Deployment IAM, local configuration and private backups are retained.

Cleanup results are recorded in the `minikube_rehearsal` section of [the evidence file](evidence/aws-rehearsal.json).

## Fix found by browser testing

Cognito sign-in succeeded but the next API request failed because OPTIONS returned HTTP 405. API Gateway supplied the expected CORS headers, so the old verifier incorrectly accepted it. The protected NGINX origin now returns 204 for OPTIONS **after** checking the gateway token. Allowed origins and authentication remain restricted. The verifier requires a successful preflight status; two regression cases reject 405/500 even when headers match. Both hosted browser logins passed after the correction. The corrected node configuration is saved in source for future deployments.

AWS documents its CORS preflight handling in [HTTP API CORS](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-cors.html). This run's observed 405 demonstrates why checking headers alone is insufficient.

## Limits to explain in the viva

- This is single-host K3s and self-managed PostgreSQL, not multi-node HA, EKS or RDS. The optional alternative was checked offline only.
- The run occurred outside booking hours. A future-date gate ticket was rejected, then only the paid disposable booking's visit date was adjusted for the positive same-day gate check. Payment/amount/status stayed unchanged. Repeat the normal business flow during valid hours without this fixture.
- Four arrivals correctly appear outside opening hours; operating-hour counts remain zero. This small dataset does not establish a business peak.
- The current 18 requests/second load stayed below the CPU scaling threshold. The earlier release observed HPA 2→3→2 under a burst with many unclassified failures; this run does not claim another scale-up or production capacity.
- New self-service signup/email confirmation was not repeated on this pool; the earlier release exercised that flow. Current demo accounts passed Cognito login and authorization.
- Local Metabase could not start because an unrelated Node process owns port 3000. It was left untouched; cloud Metabase SQL checks passed. The optional Minikube rehearsal was not repeated.
- Full-repository lint reports existing import/style issues; regression/build/format checks are separate results. Remote GitHub CI, examiner access, personal chart review, report details and submission remain manual gates.

## Next run

Follow [the demo guide](../demo.md). Use `./demo.sh up`, demonstrate the business flow and monitoring, then `./demo.sh down` and `./demo.sh audit`. Normal cleanup retains deployment IAM, local configuration, state and verified private backups. New hosted URLs/accounts are generated; prior data is not restored automatically.

## Subsequent SSH configuration change

After cleanup, Terraform was updated to reference the verified existing `sliit_test` key, add **Wonderland Demo Server** as the EC2 Name tag and permit SSH from the laptop's observed IPv4 `/32`. The 8 GiB server type is retained. These changes passed 202 regression tests, six Terraform configurations and a new read-only 45-resource plan; no new server was launched and SSH connectivity has not yet been tested live. The narrow key-use IAM update is prepared for administrator Terraform review, not applied. The live results above precede this configuration edit.
