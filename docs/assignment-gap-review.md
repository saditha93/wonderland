# Assignment readiness review — 15 October 2026

The authoritative current audit is [assignment coverage and completion gates](assignment-coverage.md), reviewed against all four pages of the supplied assignment PDF (SHA-256 `8d91c2588dc4c25db389f895a08841632f4ec810a11073b978c8a84b9c722f37`).

The core business features are implemented and locally verified. All seven rubric areas, totaling 100%, have mapped implementation paths. **The assignment is not yet fully demonstrated on AWS.** Source preparation, local tests and a read-only cloud plan do not establish live completion.

## Resolved source gaps

- Separate visitor/admin Amplify targets and publishing; exact two-origin API Gateway CORS.
- Cloud frontend demo mode explicitly disabled; real cloud date/slot rules retained.
- Smaller no-domain Terraform/K3s deployment, encrypted PostgreSQL storage/verified TLS and private Metabase/SSM access prepared.
- Simple cloud plan/deploy/release/verify/status/start/stop/monitoring commands; automatic six-hour compute stop.
- Cloud Metabase provisioning uses a separate read-only BI role and verified PostgreSQL TLS.
- Deployment permission documents validated and scoped to the reviewed account/project; no AdministratorAccess fallback.

## Evidence and outstanding work

| Area | Current evidence | Completion gap |
|---|---|---|
| Business features | Catalog, four editable tiers, booking/date/slot/guest checks, signed tickets, ownership, gate/ride histories and analytics verified locally | Integrated cloud business rehearsal |
| Authentication | Cognito SDK/signup/confirmation and JWT checks implemented | Real hosted signup/email confirmation and both roles; cross-user/admin denial |
| Payments | Stripe adapter/signature/idempotency tests; sandbox key authentication verified | Actual sandbox Checkout and delivered signed webhook; failure/duplicate handling |
| Cloud deployment | Five Terraform roots validated/mock-tested; real selected plan: 45 creations, zero deletions; non-root account and ACTIVE/FREE plan checked | Permission attachment pending; no demo server deployed; validate actual Free-plan service acceptance, bootstrap, verified API Gateway-to-IP TLS and hosted portals |
| Monitoring | Seven stored SQL questions verified locally; cloud provisioning/checks scripted | Cloud arrival/purchase/ride records and all seven queries, chart review and reconciliation |
| Non-functional requirements | Local concurrency, HPA, self-healing and recovery evidence; security/failure/cost patterns implemented | Cloud bounded load/scale, service failure and outbox recovery, deployed security inspection and cost/stop inventory |
| GitHub | Remote SSH HEAD read succeeds; workflow defined | Reviewed source publication, successful remote CI and examiner access |
| Report/viva/submission | Draft report, diagrams, guides and handover available | Actual-topology update, screenshots, links, personal review/acknowledgements, timed live IaC rehearsal and submission |

The selected design uses K3s Kubernetes and self-managed PostgreSQL on one EC2 host. It does not establish EKS, RDS, IRSA, multi-node availability or database high availability. Those belong to the retained optional advanced design. Task 8 explicitly allows Terraform; EKS/GKE are examples in Task 6. The report must explain the selected trade-offs rather than describe unused optional services as deployed.

No mandatory area should be removed to simplify commands. Refunds, cancellation, partial-party admission, seasonal pricing and MFA are not explicit mandatory features. See the current checklist for exact acceptance tests, limits and all rubric weights.
