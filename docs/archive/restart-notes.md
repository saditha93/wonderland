# Restart and demonstrate Wonderland

The completed `r20261016-tf-lifecycle7` AWS rehearsal is recorded in [the results and command guide](../results/aws-rehearsal.md). Infrastructure creation, server-side image/site builds, email confirmation/login, successful and declined Stripe sandbox payments, signed webhook retries, gate concurrency, booking/gate isolation, worker recovery, pod replacement, reporting reconciliation and seven Metabase SQL cards were observed. All 198 regression tests passed, including the guarded detached-IP cleanup retry.

A fresh backup from this deployment was downloaded and verified before Terraform teardown. The earlier run's manually terminated server had no fresh backup; that limitation does not apply to this rehearsal. Backups are private under `secrets/simple-cloud/backups/`. Restore has not been rehearsed, and `up` creates a fresh seeded demo rather than automatically restoring an old database.

Cleanup status is recorded in [acceptance evidence](../results/evidence/aws-rehearsal.json). Deployment IAM policy definitions and user attachments, local source, `.env`, target configuration, private Terraform state, logs and backups are retained. No administrator permission reinstall is needed unless policies change. Temporary cloud runtime secrets, server roles and Stripe webhook are recreated by deployment.

## Next deployment

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./cloud.sh cleanup-check
./cloud.sh up
```

Review the actual account, resource plan and cost, then type `UP`. Keep Terminal open until the entire release/verification finishes. The selected server remains the approved 8 GiB `m7i-flex.large` in us-east-1. Images and websites build on AWS; local Docker and Node are unnecessary. Changed deployment source needs a fresh immutable release identifier in the private target configuration.

```bash
./cloud.sh status
./cloud.sh verify
./cloud.sh monitoring
```

Use the actual URLs printed by `status`. Private demo logins are in `secrets/simple-cloud/accounts.json`; Metabase login is in `secrets/metabase-ec2.json`. While `monitoring` runs, open http://127.0.0.1:3001. This is a private tunnel to AWS Metabase.

New deployments generate new hosted URLs, Cognito accounts and a Stripe sandbox webhook. Real email signup needs another verification code. Do not publish `.env` or `secrets/`.

## Remaining demonstration work

Review the hosted sign-in screens and Metabase chart appearance with the user. Repeat a normal same-day booking/gate demonstration during operating hours: the previous after-hours test used one explicitly documented visit-date fixture. Burst load caused unsuccessful requests; the separate 18 requests/second test returned 2,724 successes with no errors and correctly stayed below the scaling threshold. These are demo results, not a capacity or high-availability claim.

GitHub publication/remote CI, final report/screenshots/student details and submission remain manual completion gates. Do not push without authorization.

## Finish without leaving hosted resources

Close the monitoring tunnel with Ctrl+C, then run:

```bash
./cloud.sh down
./cloud.sh cleanup-check
```

Review the deletion plan and type `DOWN`. Keep Terminal open until Terraform and the inventory audit finish. Do not manually terminate EC2 first; `down` takes a fresh database backup before destruction. Missing confirmation now fails explicitly. If cleanup fails, save the error and retry `down` with a refreshed plan. Stopping EC2 alone leaves storage/IP costs.
