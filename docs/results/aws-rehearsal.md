# Latest AWS test results

Recorded **17 October 2026**, account `459154641936`, region `us-east-1`. These are historical observations, not a claim about today's resource inventory. Run `./demo.sh audit` for a current check.

## Minikube rehearsal — 17 October 2026

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

## Verification limits

- The 18 requests/second load did not trigger HPA scale-up. It does not prove a full 2→3→2 cycle or production capacity.
- New self-service signup/email confirmation and restoration into an independent database were not repeated in this rehearsal.
- The deployment uses one EC2 host and self-managed PostgreSQL. Optional EKS/RDS was validated offline only.
- Remote GitHub CI success, examiner access and personal review of every chart remain submission checks.
- Current local UI screenshots in the Word report are labelled separately from saved AWS screenshots. They do not constitute a new cloud deployment.

## Repeat the demonstration

Follow [the demo guide](../demo.md): `up`, `status`, `check`, the normal-hours business flow, `monitor`, then `down` and `audit`. Current hosted URLs and private accounts are generated during deployment. Prior booking data is not restored automatically.

The [machine-readable evidence](evidence/aws-rehearsal.json) retains older K3s observations separately. Do not present historical after-hours fixtures or earlier scaling measurements as results of the latest Minikube run.
