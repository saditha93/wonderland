# Phase 6 outcome — Terraform and guarded cloud lifecycle

Phase 6 was authorized after Phase 5. Implementation and offline/local validation are complete for review. **No AWS account was contacted, no live Terraform plan/apply/destroy ran, no registry/Git push occurred, and no cloud or payment resource was created.** Stop before Phase 7 account access/deployment approval.

## Objectives and delivered files

Prepare real infrastructure definitions, separate persistent state from temporary cost, break the load-balancer/gateway dependency cycle, wire cloud-specific application settings, and provide lifecycle scripts that refuse unreviewed changes rather than claiming success.

- `infrastructure/terraform/advanced/bootstrap/`: protected encrypted/versioned state bucket, HTTPS-only policy, native S3 locking configuration supplied by the helper; initial local state and reviewed migration.
- `infrastructure/terraform/advanced/persistent/`: immutable ECR/lifecycle, protected Cognito public client/admin group, manual Amplify hosting, ACM DNS validation in an existing approved Route 53 zone.
- `infrastructure/terraform/advanced/demo/`: VPC/EKS/access/nodes, private RDS, SQS/DLQ, application/controller/log IRSA roles, runtime Secret shell, explicit ALB/target network rules, control/application logs, lag/DLQ alarms and SNS.
- `infrastructure/terraform/advanced/edge/`: HTTP API, private HTTPS VPC-link integration to the actual ALB listener, exact CORS origin, throttles and access logging.
- `infrastructure/terraform/advanced/modules/{network,queue}/`, pinned provider lock files and four `tests/offline.tftest.hcl` plans.
- `scripts/advanced/eks.py`, `preflight.sh`, `deploy-demo.sh`, `verify-demo.sh`, `destroy-demo.sh`: actual SDK/CLI/Terraform/Helm operations behind account, role, plan/action hash and cost guards; inventory-based cleanup checks.
- `scripts/aws/workload_templates.py`, `cloud_migrate.py`, AWS metrics-server manifest: generated TLS/Cognito/RDS/SQS/IRSA workload configuration, migration/metadata DB setup, private Metabase and scoped application log collection.
- Shared config/database/gate/analytics code: bounded cloud DB pools, required RDS certificate verification, actual selectable SQS runtime, verified internal catalog TLS, poison isolation, remote approximate queue/DLQ status, and disabled local redrive controls in SQS mode.
- `scripts/provision-metabase.py`: separate cloud login/configuration and CA-verified RDS reporting over an operator's loopback port-forward; native behavior preserved.
- `tests/test_cloud.py`, CI, locked dependencies, documentation and source attribution.

Terraform is pinned to **1.16.6**, AWS provider **6.68.0**, ALB chart/controller **1.14.1 / v2.14.1**, metrics-server **v0.8.0**, AWS for Fluent Bit **2.34.3.20261001**. The existing Metabase pin remains **0.58.35**. AWS CLI **2.38.0** and Helm **4.3.0** were installed locally. Terraform's official archive checksum was checked; no GPG-signature claim is made. Boto3/botocore are locked with the runtime dependencies.

## Workflow and acceptance

Detailed commands and approval/retention choices are in [cloud runbook](../../advanced/eks-runbook.md). Local validation:

```bash
.venv/bin/python scripts/validate-cloud.py
.venv/bin/python -m pytest -q
npm --prefix frontend run build
bash -n scripts/preflight.sh scripts/deploy-demo.sh scripts/verify-demo.sh scripts/destroy-demo.sh
```

`validate-cloud.py` downloads public provider artifacts, initializes with `-backend=false`, validates all four roots and runs mocked plans sequentially. It removes AWS environment settings for those checks; no account/API plan occurs. A future approved sequence is bootstrap plan/review/apply → reviewed state migration → persistent plan/review/apply → core plan/review/apply → reviewed image publish/controller/workloads → actual ALB discovery → edge plan/review/apply → approved Amplify publish → real verification. Persistent resources never reference temporary endpoints; the frontend is rebuilt with the current API URL.

Acceptance for Phase 6 is real parseable/provider-valid code, executable refusal paths, offline security plans and tested runtime boundaries. It is **not** a claim that AWS quotas, role permissions, versions, prices, DNS, provisioning, TLS routing, IRSA, managed auth/payment or cleanup have been verified. Those are Phase 7 acceptance criteria.

## Actual evidence — 14 October 2026

| Check | Observed result |
|---|---|
| Python suite | **118 passed**, no skips; 13 Phase 6 tests plus the existing 105. One existing upstream Starlette TestClient deprecation warning remains |
| Terraform | All four roots pass `fmt -check`, real AWS-provider schema validation and one mocked security plan each; provider lock files generated |
| Approval boundary | Real CLI preflight without authorization refused before constructing an AWS session/client; unit tests deny wrong account, root, wrong role, missing/wrong action approval, plan tampering/source drift and persistent/state destruction |
| TLS | Real local HTTPS server rejected by default trust and accepted by gate configured with its internal CA; rendered API/proxy/DB settings enforce TLS, RDS verify-full and HTTPS integration |
| SQS | Offline real-PostgreSQL tests preserve commit-before-delete/send-before-ack behavior; malformed message does not starve a valid batch item; local auth and non-AWS/wrong-region queue configurations fail closed |
| Workload schemas | Synthetic cloud render accepted by **local Minikube server-side dry run**, including HTTPS pods, migration, IRSA annotation, Ingress and private Metabase; no live apply |
| Nginx | Rendered TLS proxy configuration passes nginx's actual syntax test with ephemeral local certificates |
| Helm | Public pinned ALB chart rendered successfully offline; resolved controller image matches v2.14.1; no chart installed into EKS |
| Containers | Updated analytics and migration images built locally; both import their modules with networking disabled, without running a migration or creating an AWS client |
| Frontend/config | TypeScript/Vite build passes; Compose configuration validates; shell wrappers parse; diff whitespace clean; private files remain ignored |
| Existing local app | All four Phase 5 API readiness endpoints still return 200 through localhost:5180; its data/credentials remain separate |

Evidence is in `docs/results/evidence/phase6-2026-10-14.txt`. Generated fake credentials/certificates, manifests, plans, provider cache, signed URLs and real private configuration are not published.

Early HCL syntax errors were corrected before schema validation. Concurrent large provider processes failed to start reliably on this machine; sequential checks passed, so the reproducible checker runs sequentially. Adding the official metrics-server manifest initially exposed tests incorrectly applying application-only probe/token rules to third-party operators; tests now scope those contracts to the application manifests, with separate cloud render/privacy tests. A potential Terraform/controller SG rule ownership conflict was corrected with explicit Terraform-owned groups/rules and disabled shared backend groups. These failed intermediate checks are not counted as passes.

## Cost and deletion decisions

No target account/region/domain/version combination is selected. `cloud-target.example.json` is illustrative and contains intentionally incomplete values. The default planning capacity is two m7g.large ARM64 workers and db.t4g.small, subject to actual regional pricing/availability and quotas. No credits/Free Tier are assumed. Standard-support EKS is enforced; no NAT is provisioned. State, ECR, Cognito, Amplify, DNS/certificate records and any retained snapshots persist beyond demo teardown.

RDS deletion protection and final snapshot retention default on. Cleanup requires a separately reviewed protection update, an explicit snapshot decision, edge destruction, controller-managed Ingress/ALB deletion confirmation, then reviewed core destruction and residual audit. Bootstrap/persistent destruction is refused. KMS pending deletion, Secrets Manager recovery, retained snapshots and persistent storage must be reviewed; the script never announces zero cost merely because Terraform returned success. No destroy was run here.

## Manual actions and remaining risks

Review the source/runbook and resolve the assignment's CloudFormation-versus-Terraform ambiguity with the lecturer. Before Phase 7, choose the real account/region, non-root named-profile role, operator CIDR/AZs, supported versions, owned public DNS zone/hostname, your alert email, retention choice and private Stripe test credentials. Do not share keys in chat. Obtain explicit AWS account-access permission before preflight, then review actual plans/costs and approve each exact mutation separately.

Actual RDS master permissions/metadata ownership, EKS/IRSA/controller/SG behavior, metrics-server kubelet trust, SQS/DLQ/log/alert delivery, public Amplify/Cognito/MFA and Stripe webhook delivery remain unverified. Only sanitized API log paths are collected; the infrastructure log reader needs root access to read host logs, while application pods are non-root. Internal demo leaf certificates expire after 30 days; this is not automated production certificate management. ALB target TLS encrypts without target-certificate authentication; other internal clients verify their CA. No NetworkPolicy, node/DB HA, cloud capacity guarantee or remote CI execution is claimed. Native/Minikube operation is not proof of cloud success. Interactive UI/chart review remains pending after the prior browser security rejection.
