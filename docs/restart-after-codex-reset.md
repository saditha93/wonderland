# Restart after the Codex limit resets

AWS cleanup completed on 16 October 2026. The final inventory found no active Wonderland resources across EC2/network/EBS/public IP, S3, ECR, Amplify, Cognito, API Gateway, SQS, CloudWatch and Secrets Manager. Terraform state was reconciled after deletion. The Stripe test webhook was deleted. ECR shared layers are restored to DISABLED. Non-billable IAM policy definitions and user attachments remain.

The verified database backup, private configuration and teardown logs remain under `secrets/simple-cloud/` on this Mac. Do not upload that folder. The six built images remain in local Docker.

## What passed

- 176 local tests and visitor/admin frontend builds.
- Simple Terraform mock test and actual AWS provisioning.
- K3s Ready, SSM access, six immutable ECR images, separate Amplify websites and working visitor asset delivery.
- Cognito signup, real email confirmation and SDK login.
- PostgreSQL migration completed before the requested teardown.

Cloud application readiness, Stripe checkout/webhook, gate/ride flow, Metabase reconciliation, cloud scaling/recovery and remote GitHub CI are not complete.

## Next session

The user selected the complete 8 GiB AWS setup, retaining `m7i-flex.large` in us-east-1. Do not switch to T3. Review a fresh actual plan and cost before starting a server.

The revised lifecycle is implemented as `./cloud.sh up` and `./cloud.sh down`. See [Terraform lifecycle guide](terraform-lifecycle.md). A separate administrator Terraform root imports existing IAM definitions/attachments and corrects versioned S3 cleanup and Amplify publishing permissions. The bundle is validated but must be planned/applied in administrator CloudShell with explicit action-time permission approval. The revised live create/destroy rehearsal remains pending.

Both Terraform mock tests and 190 Python tests passed after starting the local PostgreSQL test database. These do not prove the new AWS lifecycle works live.

The deployment Python environment has been corrected to use an isolated venv with pinned boto3 and cryptography dependencies. Future source changes need a new immutable release name. Do not push GitHub without the user’s approval.

## Local demonstration while waiting

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./start.sh
```

Visitor: http://localhost:5173. Admin: http://localhost:5174.

To repeat the read-only AWS cleanup check:

```bash
./cloud.sh cleanup-check
```
