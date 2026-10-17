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
