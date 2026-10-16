# Restart after the Codex limit resets

AWS cleanup completed on 16 October 2026. The final inventory found no active Wonderland demo resources across EC2/network/EBS/public IP, S3, ECR, Amplify, Cognito, API Gateway, SQS, CloudWatch and Secrets Manager. Terraform state was reconciled and the matching Stripe test webhook removed. ECR shared layers remained disabled. Deployment IAM policy definitions and user attachments remain installed.

Local code, `.env`, target configuration, private Terraform state, logs and earlier database backups remain. Do not upload `secrets/` or `.env`. The user manually terminated EC2 before teardown, so this latest deployment has no fresh database backup; do not describe the earlier backup as current.

## Observed results

- 193 Python tests and both Terraform mock tests passed; the later cleanup confirmation fix passed all 12 lifecycle tests.
- Reviewed IAM correction and actual 45-resource Terraform provisioning passed.
- All six images and both Amplify websites built/published on the AWS server; local Docker/Node are unnecessary for cloud deployment.
- Kubernetes workloads and database migration became ready; public API, CORS, protected routes, visitor/admin login and confirmed real visitor signup passed.
- Seven stored Metabase SQL cards executed successfully against the cloud database.
- Concurrent booking creation with one idempotency key returned one booking. Stripe sandbox Checkout creation passed after removing a deprecated SDK parameter.
- Payment was not completed. Signed webhook confirmation, paid gate/ride business flow, reporting reconciliation after those events and recovery/scale demonstrations remain pending.
- Teardown removed the remaining stack. A stale IP association after external EC2 termination required a refreshed second deletion plan; final cleanup inventory was empty.

## Next session

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./cloud.sh cleanup-check
./cloud.sh up
```

Review the new plan and cost, then type `UP` only when ready to spend AWS credits. The selected configuration uses the reviewed 8 GiB `m7i-flex.large` in us-east-1. Installed IAM corrections are retained; there is no need to reinstall unchanged policies. Use a fresh immutable release name before releasing changed source. New hosted URLs and a new Stripe test webhook are generated for the rebuilt stack. Cognito accounts must also be recreated.

Continue the unfinished cloud tests. Do not push GitHub without user approval. See [Terraform lifecycle guide](terraform-lifecycle.md).

When finished:

```bash
./cloud.sh down
./cloud.sh cleanup-check
```

Type `DOWN` after reviewing the deletion plan. A missing confirmation now fails explicitly rather than appearing successful. Keep the terminal open and check the final inventory; stopped EC2 alone does not remove storage/IP costs. Cleanup preserves deployment permissions and local configuration for another run.
