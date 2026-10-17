# EC2 demo deployment permissions

The `wonderland` IAM user has AWS-managed `ReadOnlyAccess` and the four approved deployment policies below for the domain-free EC2 Kubernetes demo. They do not make the existing advanced EKS runbook compatible with the EC2 topology. The selected single-server topology is described in the main deployment guide; application resources are disposable and deployment grants are reusable.

Generate private account-specific JSON using `.venv/bin/python scripts/aws/policies.py --account YOUR_12_DIGIT_ACCOUNT_ID`. There are three managed deployment policies because the combined document exceeds AWS's 6,144-character per-managed-policy limit. The separately approved `WonderlandDemoDependencies` supplement adds required parent-resource and Cognito MFA operations. Together with `ReadOnlyAccess`, this uses five user policy attachments.

| Definition | Purpose |
|---|---|
| `WonderlandDemoCompute` | Create project-tagged networking; launch encrypted EC2 volumes and tagged `m7i-flex.large` instances only; manage/clean up tagged demo infrastructure in us-east-1. Existing tagged ENI/subnet/security group are required for launch. |
| `WonderlandDemoServices` | Project-prefixed S3 state/artifacts, ECR, SQS, Secrets Manager and logs; tagged Amplify apps/demo branches, Cognito pool and HTTP API. |
| `WonderlandDemoAccess` | Create/manage only `wonderland-demo-ec2` with the required boundary, pass it only to EC2, and run approved SSM command/session documents against tagged demo instances. Cannot attach policies to users or create/update managed policies. |
| `WonderlandDemoDependencies` | Use only the existing project-tagged VPC/subnets/security groups for dependent network creation, and configure MFA on the tagged Cognito pool. |
| `WonderlandRuntimeBoundary` | Upper bound for the EC2 role: SSM agent, project images/artifacts, queue, runtime secrets and log writes. Cannot administer IAM/EC2 or read the Terraform state bucket. **Not attached to the IAM user.** |

New resources must include `Project=wonderland` and `Stack=wonderland-demo`. Stateful bucket names must start `wonderland-demo-<account>-`; runtime images/queues/secrets/logs use the prefixes in the generated policies. Terraform matches these naming/tag constraints. Some create/authentication/agent actions need `Resource="*"`; these have action and regional conditions rather than pretending AWS supports resource-level restrictions for them. S3 and IAM scopes use bucket/role names rather than a regional endpoint restriction. This is a limited bootstrap grant, not a mathematical proof of complete least privilege.

Role creation requires `WonderlandRuntimeBoundary`; the deployer cannot edit that boundary or remove/replace it on the role. The existing role name must be absent or already have that exact boundary before installation. Role policy management alone does not bypass a permissions boundary. SSM commands intentionally permit deployment code to run on the tagged demo server; the EC2 role can read its project runtime secrets. These are security-sensitive privileges.

IAM permissions do not cap instance count/runtime, enforce the account plan, stop bills, or replace plan review. The allowed types may consume credits. No EKS, RDS, load balancer, Route 53/domain purchase, account upgrade or billing mutation is granted by these new policies. ReadOnlyAccess remains a separate broad read grant. Do not attach AdministratorAccess to the EC2 role or user.

## Setup and validation

Use the separate Terraform permissions setup in [the deployment guide](../../docs/deployment.md#one-time-permissions-setup). Normal application cleanup retains deployment policy definitions and attachments; disposable server roles are removed. This setup does not create application infrastructure. Policy simulation supports review but cannot prove every service's live tag behavior. Do not replace bounded project grants with AdministratorAccess.
