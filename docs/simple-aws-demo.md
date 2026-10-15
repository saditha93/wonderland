# Small AWS demonstration

Current status (16 October 2026): Terraform has created the AWS infrastructure, including the approved Free-plan-eligible `m7i-flex.large` server. Cognito email signup, verification and login passed. Both Amplify sites are published and the visitor UI renders. Application workload release and live payment/reporting checks are in progress; the demo is not yet verified ready. The four scoped deployment policies and separate runtime boundary are installed.

The selected topology is one x86 EC2 server running K3s Kubernetes, PostgreSQL, the four application services and Metabase. Separate Amplify websites host the visitor and admin apps; Cognito provides their identities. API Gateway forwards to the server over verified HTTPS. SQS carries reporting events. ECR holds immutable x86 images and Secrets Manager holds runtime credentials. No domain purchase is required.

This is a single-server assignment demonstration. The database and Kubernetes share one failure domain. Its encrypted local volume is persistent across stops, but it is not an RDS deployment, multi-node high-availability cluster or an off-server backup. Keep the larger EKS/RDS Terraform as the optional advanced design.

## First deployment

Use this project directory. AWS and Stripe **test** keys belong in the ignored root `.env`; do not paste them into chat. The private target is `secrets/simple-cloud/target.json`. The deployment identity is explicitly restricted to the reviewed non-root `wonderland` IAM user/account and us-east-1.

```bash
./cloud.sh plan
```

Review the resources and cost. The command prints the exact deployment command containing the saved plan digest:

```bash
./cloud.sh deploy --approve <the-digest-printed-by-plan>
./cloud.sh release
```

Plans expire after one hour and are rejected when source/target changes. Deletions/replacements are refused. Do not run the placeholder digest literally. Run `plan` again after changing deployment source.

`release` requires a running Docker engine with Linux amd64 build support and the official AWS Session Manager plugin. Both are prepared on this Mac; `cloud.sh` includes the project's private tools directory in PATH. It publishes six immutable container images, uploads a source-only node bundle, stores runtime values privately, registers a Stripe sandbox webhook if its secret is blank, installs the database and services through SSM, publishes both frontends and creates two suppressed-email demo Cognito accounts. Credentials are saved to `secrets/simple-cloud/accounts.json`; they are never embedded in frontend builds or SSM command parameters. A release name can only be reused with the same source.

The root `.env` receives the webhook secret returned by Stripe. An existing Stripe endpoint whose secret has been lost must be repaired explicitly; the helper will not silently delete it or replace its signing secret.

## Everyday commands

```bash
./cloud.sh status       # Server state and actual visitor/admin/API URLs
./cloud.sh verify       # Hosted UI, Cognito roles, CORS, TLS and workload checks
./cloud.sh monitoring   # Private Metabase tunnel at http://127.0.0.1:3001
./cloud.sh stop         # Stop compute; preserve database disk and fixed IP
./cloud.sh start        # Start compute again; allow time for readiness
```

The server automatically stops six hours after boot. Stopped compute still retains allocated IPv4 and storage; those resources can consume credits. The observed m7i-flex.large Linux/shared compute quote is $0.09576/hour, approximately $0.58 for six hours, **before** IPv4, storage, hosting, database activity and other service usage. Free-plan credits are not a promise of zero cost. The helper checks ACTIVE/FREE before mutations and never upgrades the account plan.

## Metabase setup and evidence

`release` and `verify` automatically open a temporary private tunnel and provision/query all seven cards. To view the dashboard, use `./cloud.sh monitoring`. Close that tunnel before another `verify`, which needs port 3001. For manual provisioning or repair, keep the tunnel running and use a second terminal:

```bash
.venv/bin/python scripts/provision-metabase.py \
  --env-file secrets/simple-cloud/reporting.env \
  --allow-ec2-reporting --metabase-url http://127.0.0.1:3001
```

This uses the separate read-only `wonderland_bi` database login, verified PostgreSQL TLS and seven real SQL cards. Metabase's own metadata has a separate database owner. Its admin credentials are saved privately in `secrets/metabase-ec2.json`. The dashboard is private; do not expose port 3000 or publish a public dashboard to simplify the demonstration.

## Demonstration rehearsal

1. Open the actual visitor and admin URLs printed by `status`; sign in using the private demo accounts.
2. Show attractions, four ticket tiers and the role-protected admin portal. A visitor must receive 403 from admin APIs.
3. Book an available future visit, complete Stripe **test** Checkout and confirm the signed webhook changes the booking to paid. Show the reference and signed QR ticket. Redirecting back alone must not mark it paid.
4. For a same-day gate/ride demonstration, book a valid same-day visit with an available slot. Gate admission checks the visit date; booking checks slot availability. the local after-hours simulator is not enabled on AWS.
5. Demonstrate duplicate check-in rejection, a permitted ride and the administrator's visit history.
6. Open the private Metabase dashboard. Refresh all seven cards and reconcile paid revenue, attendance and ride totals with source records.
7. Show Kubernetes readiness, the catalog HPA and the automatic stop timer through SSM. Capture evidence after actual checks; offline tests are not live deployment proof.
8. Stop compute between sessions. After testing, use the approved teardown workflow below; the default Terraform prevents accidental destruction of the server/artifact bucket.

Private Terraform state, runtime secrets and diagnostic files live under `secrets/simple-cloud/` with restricted file modes. Back them up securely outside the public artifact bucket. The server role can read project runtime material, so this single node is one trust domain; it does not provide per-pod IAM isolation.

Public IP certificates are short lived and require renewal while the server runs. The node installs a twice-daily renewal timer and checks after startup. Internal service certificates last 30 days; release refuses certificates near expiry so their rotation can be reviewed explicitly. Public login/payment traffic must never fall back to HTTP or disabled certificate validation. See the [official Certbot IP certificate instructions](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).

## Backup and complete teardown

The user has requested teardown after the live tests. Keep the terminal open until the command finishes and the inventory audit reports no remaining billable project resources.

```bash
./cloud.sh backup
./cloud.sh destroy --approve destroy-wonderland-demo
./cloud.sh cleanup-check
```

Destroy takes a fresh private database backup when deployed runtime data exists, removes the matching Stripe test webhook, destroys Terraform resources, and checks AWS inventory. Backups and state remain in the ignored private `secrets/simple-cloud/` directory on this Mac. IAM deployment policies remain installed and do not themselves incur usage charges. Stopping an instance is not complete teardown.

### Publishing permission after a fresh rebuild

Amplify assigns new app IDs when the infrastructure is recreated after destruction. Publishing permissions are deliberately restricted to the two reviewed app IDs. If AWS denies `CreateDeployment` for a newly created app, prepare the replacement grant:

```bash
.venv/bin/python scripts/prepare-demo-amplify-permission.py
```

This validates and packages the exact two-app change without altering IAM. Review and approve the printed bundle, then install it using the administrator CloudShell procedure in `infrastructure/iam/`. Do not add AdministratorAccess.
