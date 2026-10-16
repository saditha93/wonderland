# Phase 6 cloud lifecycle runbook

Implementation is prepared and checked offline. **No AWS account call, live Terraform plan, apply or destroy has been performed.** Phase 7 needs the user's explicit approval for account access and for each concrete mutation. The original phased request reserves actual AWS deployment for Phase 7. Do not infer authorization from the existence of these scripts.

## Configuration and prerequisites

Local tooling now includes Terraform 1.16.6 (verified official archive under ignored `tmp/tools/`), AWS CLI 2.38.0 and Helm 4.3.0. Terraform also accepts an installed `terraform` on PATH, but configurations require exactly 1.16.6. AWS provider is exactly 6.68.0, with committed lock files. Python dependencies include locked boto3/botocore. For a fresh checkout, install the specified Terraform release from [HashiCorp releases](https://releases.hashicorp.com/terraform/1.16.6/) and verify its SHA256SUMS, then install AWS CLI/Helm/kubectl/Docker. Run `.venv/bin/python scripts/validate-cloud.py` for provider/schema/mock checks. These download public provider artifacts and disable the S3 backend; mock tests do not use AWS credentials.

Copy `infrastructure/terraform/cloud-target.example.json` to ignored `secrets/cloud-target.json`, mode 0600, and replace every illustrative value. Supply the actual account, commercial AWS region, named profile assuming the exact non-root operator IAM role, public operator IPv4 /32, two available AZs, supported EKS standard-support version, available PostgreSQL 17 patch, existing public Route 53 zone, owned TLS hostname, your own alert email and a unique lowercase release tag. The example account/address/domain/versions are not deployment choices. No real target is selected yet. Start with [first deployment setup](account-setup.md). The existing profile/role and hosted zone/domain are prerequisites, not silently created or guessed. The operator role needs reviewed provisioning/backend/Secrets Manager/EKS permissions; workload roles are separate.

Default capacity is **two ARM64 m7g.large workers**, Single-AZ **db.t4g.small**, 20 GiB gp3 RDS, 20 GiB encrypted node volumes. This is a planning baseline with enough memory for Metabase plus workloads; it is not a regional price quote or production HA design. AWS instance/engine/add-on availability, quotas, supported versions and an actual regional estimate must be checked before a paid apply. No Free Tier is assumed. Persistent resources and retained snapshots can continue costing money after the demo is removed.

Store only Stripe **test** keys in private root `.env` (legacy `secrets/stripe.env` is a fallback) (`APP_STRIPE_SECRET_KEY=sk_test_...`, `APP_STRIPE_WEBHOOK_SECRET=whsec_...`). Never paste credentials into chat, tfvars, Git or Vite variables. Public Cognito IDs/API origins are allowed in frontend builds; backend secrets are not. The cloud worker obtains SQS credentials from its narrowly trusted IRSA service account, with no static access keys or node-role fallback expected (IMDSv2 required, hop limit one).

## Stages and state ownership

| Stage | Resources | Retention / dependency |
|---|---|---|
| `bootstrap` | Versioned, encrypted, public-blocked, TLS-only S3 state bucket | Initially local state, then explicit S3 migration; `prevent_destroy`; never removed by demo cleanup |
| `persistent` | Six immutable ECR repositories and bounded lifecycle, Cognito pool/public client/admin group, separate visitor/admin Amplify apps and manual branches, DNS-validated ACM certificate/CNAME in existing zone | No dependency on temporary stack; helper refuses persistent destruction; pool deletion protection active |
| `demo` | VPC/subnets/IGW, two EKS workers, restricted API access entry, encrypted EBS/Kubernetes secrets, private encrypted RDS, SQS/DLQ, IRSA roles, empty runtime Secret shell, explicit ALB security group, CloudWatch logs/alarms/SNS | Temporary core; no NAT. Public workers have outbound access with no public inbound rule. Private ALB and RDS subnets have no internet route |
| `edge` | API Gateway HTTP API, private VPC link and its SG, HTTPS ingress rule to the Terraform-owned ALB SG, bounded route throttling and access logs | Created only after the controller supplies the HTTPS listener ARN; removed before controller-managed ALB deletion |

Each S3 state key is `wonderland/<name>/<stage>.tfstate`, with encryption, versioning and native S3 lock files. Backend initialization and plan refresh access the account and require explicit permission too. State/plan/cache/credentials stay ignored. The helper uses a separate Terraform data directory per stage. Never destroy or empty the backend as demo cleanup.

Bootstrap migration refuses an existing remote state key and an already configured override, preventing an accidental force-copy overwrite. It creates an ignored `bootstrap/backend_override.tf` only during the approved migration. Keep the old local state backup privately until remote state is verified; do not publish or casually delete state.

## Guards and review

All cloud actions require `--allow-account-access`. Before proceeding, STS identity must match the selected account and exact configured role, and must not be root. Without that flag, no AWS session/client is created. Local refusal was exercised and unit-tested.

`plan` creates a real saved plan only after approved account access. `apply`/`destroy` require the exact saved binary SHA-256 plus `--acknowledge-costs`. The sidecar review record binds stage, target, source/configuration hashes, operation type and a 24-hour expiry. Changed/tampered/stale plans are rejected. A destruction plan cannot be passed to `apply`; bootstrap/persistent destruction is refused.

Non-Terraform mutations (`publish`, `controller`, `deploy`, `hosting`, `update-payment`, `teardown`, `migrate-state`) require an action review hash plus cost acknowledgment. Use `review --review-action <action>` to show the target/source/action before approving it. Payment updates also bind the private Stripe credential digest without displaying its contents. These flags are for a human's explicit reviewed authorization; an agent must not supply them autonomously.

The commands below are **future approved workflow examples**. Replace `REVIEWED_HASH`; do not run them just to test a guard against a real account.

```bash
# Read-only account/version preflight, only after access is explicitly approved:
.venv/bin/python scripts/advanced/eks.py preflight --allow-account-access
# Bootstrap: plan, review target/cost/output, then separately approve apply:
.venv/bin/python scripts/advanced/eks.py plan --stage bootstrap --allow-account-access
.venv/bin/python scripts/advanced/eks.py apply --stage bootstrap --allow-account-access --acknowledge-costs --approve-plan REVIEWED_HASH
# Review and approve migration before persistent/demo plans:
.venv/bin/python scripts/advanced/eks.py review --review-action migrate-state
.venv/bin/python scripts/advanced/eks.py migrate-state --allow-account-access --acknowledge-costs --approve-action REVIEWED_HASH
# Repeat plan → review → approved apply for persistent, then demo:
.venv/bin/python scripts/advanced/eks.py plan --stage persistent --allow-account-access
.venv/bin/python scripts/advanced/eks.py apply --stage persistent --allow-account-access --acknowledge-costs --approve-plan REVIEWED_HASH
.venv/bin/python scripts/advanced/eks.py plan --stage demo --allow-account-access
.venv/bin/python scripts/advanced/eks.py apply --stage demo --allow-account-access --acknowledge-costs --approve-plan REVIEWED_HASH
```

Always review the actual Terraform output, time window, regional costs, snapshot retention and SNS email confirmation behavior. A local mock plan is not a cloud plan. EKS standard support is enforced in configuration/preflight to avoid silently opting into extended-support billing. Costs/quotas and actual IAM permissions remain unverified.

## Images, controller, migrations and workloads

For each mutation, first run the `review` action and get explicit approval of the printed digest, then execute with the required flags. Sequence:

1. `publish`: build six **linux/arm64** images, authenticate ECR through stdin, push unique immutable tags and log out. No push occurs during Phase 6. Do not reuse an existing release tag.
2. `controller`: write the dedicated ignored `secrets/aws.kubeconfig` from the exact EKS cluster, install ALB chart **1.14.1 / controller v2.14.1**, install vendored metrics-server **v0.8.0**, and deploy a pinned Fluent Bit node collector. The official controller IAM policy is vendored from the matching release. The collector trusts only its kube-system service account and writes only the project's application log group.
3. `deploy`: fetch the managed RDS master secret and project runtime Secret value without logging them. On first use, generate service/BI/metadata credentials and RSA ticket keys privately and store them in Secrets Manager outside Terraform state. Keys/passwords are reused on subsequent deployments. Generate/reuse a private demo internal CA/individual TLS certificates. Apply separate service Secrets on stdin using server-side apply (no last-applied secret annotation).
4. Run a versioned migration Job with the owner credential: migrations/seeds/role grants, then separately owned PostgreSQL Metabase metadata database. It models RDS's non-superuser master by granting the new metadata owner role before database creation. Wait for completion; remove the owner Secret; completed Job has a five-minute TTL. Owner credentials never go to API pods.
5. Roll out the four APIs, HTTPS nginx and private Metabase. Each API gets its own restricted DB credential; only booking receives the ticket private key. No local identity secret is distributed. API databases use `sslmode=verify-full` and the checked-in official RDS CA bundle. Both gateway-to-ALB and nginx/gate-to-API traffic use TLS. nginx/gate verify the internal CA. ALB encrypts target traffic but, by AWS design, does not authenticate target certificates; this is not mutual TLS.
6. `discover`: confirm the actual internal ALB belongs to the approved VPC and uses its reviewed security group, then save the HTTPS listener ARN for `edge` variables. Plan/review/apply `edge` separately.
7. `hosting`: build both React apps with public Cognito IDs, the newly created API URL and demo mode explicitly disabled. Publish `dist` to the visitor Amplify app and `dist-admin` to the admin app. Each archive contains the build contents at its root. Upload using Amplify's signed upload URL (never logged), start each manual deployment and wait for confirmed completion. Both origins are passed into edge CORS. Persistent hosting configuration does not reference demo resources.
8. `verify`: check both hosted URLs, preflight CORS for both origins, rejection of an unapproved origin, real HTTPS API readiness, anonymous denial and approximate DLQ count. This does **not** claim authenticated, provider-payment or end-to-end success. Complete the Phase 7 rehearsal checklist below.

Cloud workload rendering is code in `scripts/aws/workload_templates.py`, rather than copying local-mode manifests into EKS. It adds TLS, Cognito, RDS URLs, bounded pools, IRSA, ECR tags, separate metadata/BI credentials, secret checksums to trigger controlled rollout on updates, and preferred replica separation across worker nodes. Local Minikube manifests and data remain separate.

Terraform owns ALB/frontend network rules, and shared controller backend groups are disabled. This prevents controller reconciliation from undoing Terraform rules or leaving a shared backend SG after teardown. Only VPC-link HTTPS reaches the ALB; ALB targets use TCP 8443. Database ingress is from the cluster/node group. These security groups are not per-service NetworkPolicies.

The log collector reads **only** the project's `api` container log paths, not vendor Metabase, migration or arbitrary namespaces. Application logs are already sanitized JSON. Its host-log reader runs as root with read-only host logs, no privilege escalation, dropped capabilities and scoped IRSA; application pods remain non-root. Actual delivery, redaction and alerting must be verified in AWS. Control-plane/application/API logs have seven-day retention. SNS requires confirmation by the supplied user email. No email was sent in Phase 6.

Metrics-server kubelet trust and actual resource metrics must be verified on the selected EKS version; the manifest does not disable TLS verification. If it is unready, resolve serving-certificate trust or use an approved compatible managed add-on before claiming cloud HPA. No EKS/Helm/IRSA/RDS integration success is inferred from local rendering/schema checks.

## Stripe endpoint and private Metabase

The actual webhook URL is `<api_url>/api/booking/payments/webhook`. Initial cloud rollout can use an existing **test** signing secret; after edge creation, configure this endpoint in the Stripe test account and update the private signing secret. Run reviewed `update-payment` to update the existing runtime Secret and roll booking with a changed secret checksum. Live Stripe test delivery remains unverified; no production key or real payment is allowed. Payment-account/identity changes need separate consideration for pending bookings; do not casually rotate accounts.

Metabase uses an owned RDS metadata database, not H2, and a separate read-only BI login for aggregate reporting. There is no public Metabase Ingress. After approved deployment, use the dedicated EKS context to port-forward privately:

```bash
kubectl --kubeconfig secrets/aws.kubeconfig --context wonderland-aws-YOUR_NAME -n wonderland port-forward --address=127.0.0.1 service/metabase 3001:3000
# Another terminal, after /api/health responds:
.venv/bin/python scripts/provision-metabase.py --allow-cloud-reporting --metabase-url http://127.0.0.1:3001 --env-file secrets/cloud-reporting.env
```

The Kubernetes API tunnel encrypts remote forwarding; browser/API access on the operator's loopback remains local HTTP. JDBC verifies the RDS CA. Cloud Metabase login details are stored separately in private `secrets/metabase-cloud.json`. Provisioning verifies all seven stored SQL questions; no public sharing link is created. Native Metabase remains independent. Internal leaf certificates last 30 days, their CA 90 days: this is a short demo certificate approach, not automated production certificate management. Expiration/rotation requires a separately reviewed maintenance plan.

## Destruction and residual audit

Default RDS deletion protection is **on**, and final snapshot retention is **on**. For cleanup, explicitly decide snapshot retention/unique name and update `allow_database_destroy=true`; generate/review/apply that protection change before a core destruction plan. The helper checks actual RDS protection, not only the input flag. Retained snapshots incur storage charges and can conflict with a reused name. Setting `retain_final_snapshot=false` deliberately discards the demo DB on destroy and needs explicit plan approval.

1. Save/review/approve the **edge destroy** plan: `deploy-demo.sh plan --stage edge --destroy --allow-account-access`, then `destroy-demo.sh --stage edge ... --approve-plan REVIEWED_HASH`.
2. Review/approve `teardown`. It refuses nonempty edge state, removes the Ingress while the controller is running, waits for confirmed ALB deletion, then removes the application namespace. Do not delete the EKS cluster first.
3. Generate/review/approve the **demo destroy** plan. The helper refuses surviving namespace/ALBs or database protection. A partial cleanup can be resumed with a fresh plan when the relevant cluster/DB is already gone; remaining dependencies must still pass checks.
4. Run approved account-read `audit`. It inventories project tags, EKS, RDS/manual snapshots, EBS, load balancers, queues, public address allocations and retained ECR. Recorded VPC identifiers permit checks for leftover ENIs, NAT, VPC endpoints and SGs after a partial destruction. The private report is `secrets/cleanup-audit.json`.
5. Inspect persistent state/ECR/Cognito/Amplify/DNS/certificates, snapshots, pending KMS deletion and Secrets Manager recovery. The script makes **no zero-cost claim**. Account-wide reads may include other clusters; it never deletes them. Residual resources require a reviewed decision, not blanket deletion.

```bash
.venv/bin/python scripts/advanced/eks.py plan --stage edge --destroy --allow-account-access
.venv/bin/python scripts/advanced/eks.py destroy --stage edge --allow-account-access --acknowledge-costs --approve-plan REVIEWED_HASH
.venv/bin/python scripts/advanced/eks.py review --review-action teardown
.venv/bin/python scripts/advanced/eks.py teardown --allow-account-access --acknowledge-costs --approve-action REVIEWED_HASH
# After a separately reviewed protection update, and with explicit snapshot decision:
.venv/bin/python scripts/advanced/eks.py plan --stage demo --destroy --allow-account-access
.venv/bin/python scripts/advanced/eks.py destroy --stage demo --allow-account-access --acknowledge-costs --approve-plan REVIEWED_HASH
.venv/bin/python scripts/advanced/eks.py audit --allow-account-access
```

If the controller/cluster was destroyed before its ALB, the helper stops and the audit identifies residual dependencies. Do not claim cleanup success or remove another project's resources to force VPC deletion. Resolve exact orphan resources under a separate reviewed cleanup authorization. This runbook is not evidence that teardown has actually run.

## Phase 7 rehearsal still required

Confirm real target/version/price/quotas and role permissions; inspect every live plan; test DNS/ACM validation, IRSA, TLS identity, RDS/migration/metadata ownership, metrics-server trust, controller/SG lifecycle, public Amplify signup/confirmation/login/MFA/admin denial, Stripe signed test webhook, stored Metabase SQL, SQS poison/replay/DLQ/alerts, pod/worker/DB failures, HPA and blue-green. Review actual CloudWatch logs for leakage; record timings/screenshots and the cleanup inventory. Assignment CloudFormation-vs-Terraform ambiguity still needs lecturer clarification. Stop after Phase 6 review until account access is explicitly approved.

## Primary references used

- [Terraform S3 backend and native lock files](https://developer.hashicorp.com/terraform/language/backend/s3)
- [AWS HTTP API private integrations and TLS](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html)
- [EKS IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/associate-service-account-role.html)
- [Pinned controller security-group ownership behavior](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v2.14.1/docs/deploy/security_groups.md)
- [AWS for Fluent Bit pinned release](https://github.com/aws/aws-for-fluent-bit/releases/tag/v2.34.3.20261001)
- [Metabase metadata database, separate user/password variables and TLS](https://www.metabase.com/docs/latest/installation-and-operation/configuring-application-database)
- [Official RDS CA bundle](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem)
