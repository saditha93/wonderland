# Terraform: start and remove the AWS demo

The selected deployment keeps everything in AWS: one 8 GiB `m7i-flex.large` server in `us-east-1`, separate visitor/admin Amplify websites, Cognito, ECR, SQS, API Gateway, private artifacts and runtime secrets. PostgreSQL and Metabase run on the server. The live deployment was destroyed on 16 October 2026; the final AWS inventory found no active demo resources. Deployment IAM policies and local configuration are retained.

## One-time permissions setup

Application Terraform cannot grant its own deployment user extra access. A separate administrator Terraform root in `infrastructure/terraform/permissions/` imports the existing five project policy definitions and four deployment attachments. It keeps the runtime boundary separate and retains the existing ReadOnlyAccess attachment. This setup creates no server.

On this Mac:

```bash
cd /Users/sadithaudayanga/Projects/wonderland
.venv/bin/python scripts/aws/prepare_permissions.py
```

The read-only helper validates policies with AWS and creates `secrets/simple-cloud/terraform-permissions.zip`. Upload only this ZIP using administrator CloudShell's Actions → Upload file. It contains policy definitions and the bootstrap runner, without keys, application secrets or application state.

In CloudShell, extract the ZIP, then run the exact plan command printed by the helper:

```bash
unzip -o ~/terraform-permissions.zip -d ~/wonderland-permissions-review
cd ~/wonderland-permissions-review
# Paste the printed python3 bootstrap.py --bundle ... --review ... command here.
```

Review the actual IAM Terraform plan. After explicit approval, rerun that same command with `--apply` followed by the saved IAM plan digest. Plans expire after an hour. The runner rejects deletion/replacement and verifies the final policy documents and attachments. The runner places large provider downloads in private temporary storage, moves any previous failed home-directory cache there, and reinitializes providers when needed. Administrator state stays under `~/.wonderland/terraform-permissions/459154641936/` in CloudShell; preserve it privately. Application teardown retains these non-billable policies so future deployments remain possible.

The installed correction adds project-scoped S3 object-version deletion and publishing resources under this account’s Amplify `demo` branches. App/branch management requires project ownership tags; deployment/job publishing uses account, region and branch limits because AWS omits app tags from those child-resource checks. The application `up` command refuses to create resources while the S3 cleanup permission is absent. The corrected policy is installed and verified; both live portals were published successfully.

## Everyday use

Keep AWS and Stripe sandbox credentials in the ignored root `.env`. Keep the private target in `secrets/simple-cloud/target.json`. Source changes require a fresh immutable release name; do not reuse the previous `r20261016-demo5` for changed source.

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./cloud.sh up
```

The command previews the actual Terraform plan, account, region and cost, then asks you to type `UP`. It applies the reviewed plan and releases the application. Terraform manages AWS infrastructure. The release helper builds/publishes containers and both websites on the AWS node, installs Kubernetes workloads through SSM, and publishes the website artifacts to Amplify. Local Docker and Node.js are not needed. A temporary project-scoped ECR token and signed artifact-upload URLs are fetched privately from Secrets Manager and removed from its current value after each build; no static AWS keys enter the node or source bundle. Keep the terminal open until verification finishes. A failed release may leave infrastructure running: use `status`, investigate, then retry `release` or remove it with `down`.

```bash
./cloud.sh status
./cloud.sh verify
./cloud.sh monitoring
```

`status` prints the real website/API URLs. `monitoring` opens a private Metabase tunnel at http://127.0.0.1:3001; keep that terminal open while viewing it. Private login details stay in `secrets/simple-cloud/accounts.json` and `secrets/metabase-ec2.json`.

Remove the demo after testing:

```bash
./cloud.sh down
./cloud.sh cleanup-check
```

`down` previews resource deletions and asks you to type `DOWN`. It backs up an existing database to this Mac, refreshes Terraform state, updates deletion-protection/force-delete settings through Terraform, destroys the approved infrastructure, removes the matching Stripe test webhook and checks AWS inventory. A failed backup blocks destruction. If you already terminated the server, it reports that a fresh backup is impossible and preserves prior local backups. If the server is stopped, run `./cloud.sh start` and wait for readiness before `down` so backup can succeed.

Cleanup retains deployment IAM policy definitions/attachments, local `.env`, Terraform configuration/state and backups. Disposable server IAM roles are recreated on the next deployment. The matching temporary Stripe webhook is removed because its deleted API endpoint cannot receive events.

If an apply fails leaving only a detached demo IP after server termination, cleanup refreshes state and retries Terraform once within the approved scope. It refuses to retry automatically if a server is still active, an IP remains associated, or another resource remains. For other errors, inspect the log, rerun `./cloud.sh down` with a fresh plan, then `./cloud.sh cleanup-check`. Never interpret an error as completed cleanup.

Stopping with `./cloud.sh stop` preserves storage and public IP, which can still consume credits. Complete teardown requires `down` and a successful inventory check. Private backups, logs and application Terraform state remain under `secrets/simple-cloud/`; never commit or publish that directory.

## Preview and automation

Without an interactive terminal, `up` and `down` only preview and print the exact approval command. Unconfirmed `down` exits with an error explicitly stating cleanup was not executed. Use the digest from that run, without angle brackets:

```bash
./cloud.sh plan
./cloud.sh up --approve <printed-deployment-digest>
./cloud.sh plan-down
./cloud.sh down --approve <printed-teardown-digest>
```

Approval expires after an hour and is bound to source, target and plan. Teardown also binds state and the permitted deletion scope. Overlapping mutating commands are rejected. For an infrastructure-only rehearsal, use `./cloud.sh up --infra-only`; it skips application release. Teardown still uses `down`.

The observed compute quote is $0.09576/hour, about $0.58 for six hours, plus IPv4, storage and other services. Review the fresh plan's quote before starting. Free-plan credits cover eligible usage while available; the helper never upgrades the account. The server has a six-hour automatic stop timer, which does not remove other resources.

## Verification status

Both Terraform mock tests and 198 Python tests passed. The complete 45-resource creation/server-side release and live acceptance checks were observed in release `r20261016-tf-lifecycle7`. This includes real email confirmation/login, admin/ownership checks, successful and declined Stripe sandbox payments, signed webhook deduplication, concurrent gate admission, booking/gate isolation, worker recovery, pod replacement, reporting reconciliation and Metabase SQL cards. A fresh database backup was verified before teardown.

See [the detailed results](results/aws-rehearsal.md) for the after-hours date fixture, burst/load interpretation and remaining manual assignment gates. Cleanup status is recorded in [acceptance evidence](results/evidence/aws-rehearsal.json). Deployment IAM policies and local configuration are retained for reuse.
