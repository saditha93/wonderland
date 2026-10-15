# Assignment readiness review — 15 October 2026

Reviewed against the supplied four-page assignment PDF, particularly pages 2–4, and current source/configuration. The supplied PDF matches the private course-materials copy (SHA-256 `8d91c2588dc4c25db389f895a08841632f4ec810a11073b978c8a84b9c722f37`).

## Implementation update after review

The admin hosting/CORS and cloud demo-setting gaps below are now fixed in source. Both frontend builds, 19 focused cloud tests and all four Terraform validation/mock plans passed. Hosted URL/CORS checks were added to the live verifier. This remains offline evidence; no AWS account call or paid resource creation has occurred. See [first deployment setup](aws-first-deployment.md) for the missing target details. The table below retains the original audit findings.

## Verdict

The local MVP has the main required business features. It is ready to proceed toward infrastructure work **with separate admin hosting and CORS now fixed in source**. The assignment is not yet fully demonstrated: managed registration, external test payments, actual cloud deployment and assessment evidence remain pending.

This is a source/document review. It does not claim a fresh test run or a cloud deployment. Previously recorded evidence includes 149 passing Python tests, both frontend builds, 14 local infrastructure stages and seven Metabase SQL questions verified against stored data. See [validation](validation.md).

## Gaps and when to resolve them

| Item | Current evidence and gap | Next action |
|---|---|---|
| Separate admin cloud URL — fix before deployment | `scripts/cloud.py` hosting packages only `frontend/dist`; `frontend/dist-admin` is not published. `infrastructure/terraform/persistent/main.tf` defines one Amplify app/branch. `infrastructure/terraform/edge/main.tf` allows only the visitor origin. | Add a separate admin hosting target, publish its build, expose its URL and allow both explicit origins. Include admin access and visitor-role denial in cloud smoke checks. |
| Cloud demo setting — fix before deployment | The hosting environment enables Cognito but does not explicitly override inherited `VITE_DEMO_MODE`. Backend cloud date validation remains enforced. | Explicitly disable the frontend demo setting in cloud builds. |
| Visitor registration — verify with managed auth | Local mode offers preconfigured password accounts. The signup form in `frontend/src/AuthPanel.tsx` is shown only in Cognito mode. SDK signup/confirmation/login and offline JWT checks exist; actual managed signup is unverified. | Exercise a new account through signup, email confirmation, login, own booking/history and denied admin/cross-user requests after Cognito provisioning. |
| Payment integration — verify before final demonstration | Stripe adapter, signed webhook and idempotency checks exist. Local simulator/offline tests do not prove an actual provider checkout. | Use Stripe test mode for checkout, failed payment and delivered signed webhook; verify stored amount and duplicate handling. No real-money transaction is needed. |
| Cloud infrastructure — verify during infrastructure phase | Terraform/Kubernetes configuration and local fault/scale evidence exist. Actual EKS, AWS API Gateway, RDS, SQS/IRSA, Amplify, Cognito, TLS, encryption, alerts and cleanup remain unverified. No private cloud target has been selected. | Review target account/role/region, domain, budget and retention choices before approved provisioning; then record real health, security and lifecycle evidence. |
| Metabase — reconnect and demonstrate | Native dashboard and seven SQL questions use actual native database facts. Native and local Kubernetes databases are separate environments. Chart appearance remains manually unreviewed. | Connect Metabase to the deployed environment's read-only reporting data; demonstrate arrivals, tier sales/revenue, popular rides and peak/quiet hours, with source reconciliation and screenshots. |
| GitHub integration — verify remotely | A GitHub remote and workflow definition exist. Remote repository access and a successful remote workflow run have not been verified in this audit. | Confirm the submitted repository link works and retain a successful GitHub Actions run. |
| Report/viva — manual closeout | Report, diagrams and guides are prepared. Personal review, live screenshots, cloud evidence, working submission links and timed full-stack IaC rehearsal remain pending. | Update the report with actual results, review understanding/acknowledgements and rehearse deployment plus cleanup for the viva. |

## Required local functionality already covered

- Attraction descriptions, category, thrill and suitability; protected admin create/update/retire.
- Four database-stored editable booking tiers, guest/date/slot validation and immutable booked-price snapshots.
- Local payment simulation, signed QR/reference, owned booking/visit/ride history and profile access.
- Protected gate check-in, full-party guest counts, duplicate rejection and timestamped ride usage.
- Durable events, reporting projections and stored-data analytics for arrivals, purchases, rides and busy/quiet periods.
- Containerized services, local Kubernetes persistence, scaling, self-healing and failure-recovery evidence.

These local checks do not establish managed cloud functionality or production availability. Interactive visitor/admin/mobile appearance still needs manual review.

## Recommended order

1. Fix admin publishing, both allowed origins and the cloud demo setting.
2. Select and review the private cloud target, estimated cost and retained resources.
3. Provision and test the managed authentication, application, database, queue and HTTPS paths.
4. Exercise real Stripe test checkout/webhook and reconnect Metabase to that environment.
5. Verify GitHub Actions, capture manual evidence and finish the report/live IaC rehearsal and cleanup audit.

Do not expand the MVP merely for this audit: refunds, cancellation, partial-party arrival, seasonal prices and MFA are not explicit mandatory features in this assignment. Document existing assumptions instead. The assignment's page 3 names CloudFormation for AWS while page 4 allows CloudFormation or Terraform; lecturer confirmation of Terraform on AWS remains advisable.
