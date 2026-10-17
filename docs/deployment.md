# Terraform: start and remove the AWS demo

The selected deployment keeps everything in AWS: one 8 GiB `m7i-flex.large` server in `us-east-1`, separate visitor/admin Amplify websites, Cognito, ECR, SQS, API Gateway, private artifacts and runtime secrets. PostgreSQL and Metabase run on the server. The latest live deployment was destroyed; the final AWS inventory found no active demo resources. Deployment IAM policies and local configuration are retained.

## Minikube and Ingress on the server

The current server bootstrap installs **Minikube v1.39.0** and **kubectl v1.36.5**. Minikube runs as `ubuntu` with the Docker driver and containerd, two CPUs and 5 GiB assigned to the cluster on the 8 GiB EC2 host. Docker is the Linux driver dependency; there is no Helm or separate controller installation. The built-in `ingress` and `metrics-server` add-ons supply routing and HPA metrics. Systemd starts the same persistent cluster after a reboot. A dependent `wonderland-routing` service restores the TLS certificate and Ingress settings after Minikube reapplies its add-on defaults.

The request path is Amplify → API Gateway → protected host HTTPS proxy → Minikube Ingress → Kubernetes Service → API pod. Ingress strips `/api/booking`, for example, before forwarding `/bookings` to the booking service. Each hop verifies its TLS peer. The obsolete in-cluster frontend proxy is omitted because Amplify already hosts the websites. PostgreSQL and Metabase have no public Ingress rules. The security group still exposes only 80/443 and SSH from the laptop's `/32`; Kubernetes and the Docker node stay private.

The four readable rules are in [ingress.yaml](../infrastructure/kubernetes/aws/ingress.yaml). The bootstrap automatically enables the add-ons, and the release applies the rules with kubectl. For your viva, SSH as `ubuntu` and run:

```bash
minikube -p wonderland status
minikube -p wonderland addons list
kubectl get nodes
kubectl -n wonderland get pods,svc,ingress,hpa
kubectl -n wonderland describe ingress api-booking
kubectl -n ingress-nginx get pods
kubectl -n wonderland top pods
```

Expected: the node is Ready, all four Ingress objects use class `nginx`, API Services are internal ClusterIP, and the Ingress controller is ready. `/api/attractions/health` through the API Gateway URL checks actual routing. `./demo.sh check` also checks hosted API access and private Metabase. Use `./demo.sh down` on the laptop for complete AWS teardown; `minikube stop` alone leaves chargeable AWS resources allocated.

This is a lab demonstration. Minikube's bundled ingress-nginx controller was [retired in March 2026](https://github.com/kubernetes/ingress-nginx/blob/main/README.md) and receives no further fixes. This choice follows the requested built-in add-on rather than adding another controller. The server disk is encrypted by EBS; the former K3s-specific secrets-encryption option does not apply to Minikube. The node instance role remains shared by workloads in this trusted single-node demo; IMDSv2 is required with a hop limit of three for Docker-node/pod networking.

The Minikube change has now been deployed and tested on AWS, including all four Ingress routes, Cognito roles, real Stripe sandbox success/decline, gate concurrency, service isolation, worker recovery and Metabase queries. See the latest [rehearsal results](results/aws-rehearsal.md). Replacing an existing K3s server is not an in-place database migration: first use `down` for its verified backup and teardown. From a clean state, deploy with the ordinary `up` command and a fresh release identifier.

## Required tools and private configuration

This project's laptop already has its private target, credentials, permissions and tool binaries. Keep those files; do not overwrite them during the reorganization.

For a fresh machine, install Python/Node/uv as described in the README, AWS CLI and Session Manager plugin, and Terraform **1.16.6**. The controller prefers `terraform` on PATH and otherwise uses `tmp/tools/terraform`. The provider is pinned by the checked-in lock files. The root target is selected explicitly; the optional EKS/RDS configuration is separate.

Copy `infrastructure/terraform/aws/target.example.json` to the ignored `secrets/simple-cloud/target.json`, replacing the account and AMI placeholders. Select an available official Ubuntu x86-64 AMI owned by `099720109477` in us-east-1; `up` verifies owner, architecture, server eligibility and memory before creation. The availability zone can be omitted so preflight selects an offered zone. Use a fresh lowercase release identifier when source changes.

Root `.env` holds the reviewed non-root AWS credentials and a Stripe `sk_test_` key. For a new deployment, leave `APP_STRIPE_WEBHOOK_SECRET` blank: the release helper creates the matching sandbox endpoint after the API URL exists and stores the signing secret privately. Never put AWS or Stripe secrets in `VITE_` variables. The original project's reusable IAM grants remain installed; new accounts require the separate reviewed administrator setup below.

Use `./demo.sh` for the normal viva sequence. `cloud.sh` exposes additional planning/recovery commands; they use the same implementation.

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

Keep AWS and Stripe sandbox credentials in the ignored root `.env`. Keep the private target in `secrets/simple-cloud/target.json`. Source changes require a fresh immutable release name; do not reuse an identifier from a different source revision.

```bash
cd /Users/sadithaudayanga/Projects/wonderland
./cloud.sh up
```

The command prints the actual Terraform plan, account, region and cost, then applies that saved plan and releases the application without another prompt. Use `./demo.sh plan` for a preview without applying. Terraform manages AWS infrastructure. The release helper builds/publishes containers and both websites on the AWS node, installs Kubernetes workloads through SSM, and publishes the website artifacts to Amplify. Local Docker and Node.js are not needed. A temporary project-scoped ECR token and signed artifact-upload URLs are fetched privately from Secrets Manager and removed from its current value after each build; no static AWS keys enter the node or source bundle. Keep the terminal open until verification finishes. A failed release may leave infrastructure running: use `status`, investigate, then retry `release` or remove it with `down`.

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

`down` creates and applies its validated deletion plan without another prompt. Use `./demo.sh plan-down` to preview without deleting. It backs up an existing database to this Mac, refreshes Terraform state, updates deletion-protection/force-delete settings through Terraform, destroys the approved infrastructure, removes the matching Stripe test webhook and checks AWS inventory. A failed backup blocks destruction. If you already terminated the server, it reports that a fresh backup is impossible and preserves prior local backups. If the server is stopped, run `./cloud.sh start` and wait for readiness before `down` so backup can succeed.

Cleanup retains deployment IAM policy definitions/attachments, local `.env`, Terraform configuration/state and backups. Disposable server IAM roles are recreated on the next deployment. The matching temporary Stripe webhook is removed because its deleted API endpoint cannot receive events.

If an apply fails leaving only a detached demo IP after server termination, cleanup refreshes state and retries Terraform once within the approved scope. It refuses to retry automatically if a server is still active, an IP remains associated, or another resource remains. For other errors, inspect the log, rerun `./cloud.sh down` with a fresh plan, then `./cloud.sh cleanup-check`. Never interpret an error as completed cleanup.

Stopping with `./cloud.sh stop` preserves storage and public IP, which can still consume credits. Complete teardown requires `down` and a successful inventory check. Private backups, logs and application Terraform state remain under `secrets/simple-cloud/`; never commit or publish that directory.

## Preview and automation

`up` and `down` perform their named actions in interactive terminals and automation alike. They retain account, scope, source, state and saved-plan checks. For manual plan/apply separation, use the preview commands and optionally pass the printed digest:

```bash
./cloud.sh plan
./cloud.sh up --approve <printed-deployment-digest>
./cloud.sh plan-down
./cloud.sh down --approve <printed-teardown-digest>
```

Approval expires after an hour and is bound to source, target and plan. Teardown also binds state and the permitted deletion scope. Overlapping mutating commands are rejected. For an infrastructure-only rehearsal, use `./cloud.sh up --infra-only`; it skips application release. Teardown still uses `down`.

The observed compute quote is $0.09576/hour, about $0.58 for six hours, plus IPv4, storage and other services. Review the fresh plan's quote before starting. Free-plan credits cover eligible usage while available; the helper never upgrades the account. The server has a six-hour automatic stop timer, which does not remove other resources.

## Verification status

All six Terraform configurations and 212 Python tests passed for the Minikube source update; both website builds passed. The Minikube live acceptance and restart checks also passed; see the latest results. The complete 45-resource creation/server-side release and live acceptance checks were repeated in release `r20261017-tf-lifecycle8`. Browser login initially failed because the protected origin forwarded OPTIONS to services that returned 405; the proxy now returns 204 after its gateway-origin check, and verification requires a successful preflight status. Visitor and administrator browser login passed afterward. This includes real email confirmation/login, admin/ownership checks, successful and declined Stripe sandbox payments, signed webhook deduplication, concurrent gate admission, booking/gate isolation, worker recovery, pod replacement, reporting reconciliation and Metabase SQL cards. A fresh database backup was verified before teardown.

See [the detailed results](results/aws-rehearsal.md) for the after-hours date fixture, burst/load interpretation and remaining manual assignment gates. Cleanup status is recorded in [acceptance evidence](results/evidence/aws-rehearsal.json). Deployment IAM policies and local configuration are retained for reuse.

## Optional EKS/RDS design

The retained alternative lives under `infrastructure/terraform/advanced/` and `scripts/advanced/eks.py`. It uses separate bootstrap, persistent, demo and edge states, EKS workers, private RDS, an internal load balancer, API Gateway VPC link and workload IAM roles. It requires its own `secrets/cloud-target.json`, existing domain/hosted zone, toolchain and separately reviewed cost/permission plan. It has only been checked offline; the EC2/K3s rehearsal does not verify this topology.

Use `.venv/bin/python scripts/advanced/eks.py --help` to inspect commands. Its lifecycle stages are bootstrap → persistent → demo → application/controller → edge; teardown reverses dependencies and retains protected persistent state. Use the main `./demo.sh` workflow for this assignment demonstration unless deliberately choosing the alternative.

## Laptop SSH and server name

The server remains `m7i-flex.large` (8 GiB), the tested eligible full-stack size. The account's Free plan marks T3 Small as eligible but it has only 2 GiB; T3a Medium has 4 GiB and is not eligible. No account upgrade or server launch was made for this configuration change.

Terraform references the existing `sliit_test` EC2 key pair and sets the EC2 `Name` tag to **Wonderland Demo Server**. The matching private key stays at `~/Projects/pem/sliit_test.pem`; it is never uploaded or stored in Terraform. Port 22 accepts only `112.135.65.45/32`, the laptop's public IPv4 observed on 17 October 2026. Database, Kubernetes and Metabase ports remain private, and SSM still works.

The private target contains `server_name`, `ssh_key_name`, `ssh_private_key_path` and `ssh_allowed_cidr`. If your public IP changes, update `ssh_allowed_cidr` to the new IPv4 plus `/32` before reviewing a fresh plan. Broad SSH networks are rejected. The server's Ubuntu AMI uses the `ubuntu` login:

```bash
chmod 400 ~/Projects/pem/sliit_test.pem
./demo.sh status
ssh -i ~/Projects/pem/sliit_test.pem ubuntu@SERVER_PUBLIC_IP
```

Replace `SERVER_PUBLIC_IP` with the output of `status`; Terraform also outputs the complete SSH command. The existing key pair is referenced, not created or deleted by demo cleanup.

Launching with a key pair requires an additional `ec2:RunInstances` permission for that exact key-pair ARN. The separate Terraform permission generator includes that narrow grant. Use the one-time permissions procedure above to review/apply the new bundle before the next deployment; `up` checks it before creating resources. No installed IAM grants were changed by this edit.

The SSH correction scopes `RunInstances` to `key-pair/sliit_test` (the key **name**). EC2 does not authorize this launch against the `key-*` ID. The first prepared grant used the ID and was denied; the corrected bundle is `secrets/simple-cloud/terraform-permissions-ssh-name.zip`. Apply its reviewed administrator Terraform plan, then rerun `./demo.sh up` to resume the partial stack. The source preflight now checks the same name ARN that EC2 uses.

The generated private `secrets/simple-cloud/install-wonderland-permissions.sh` packages the validated permission bundle for a single administrator CloudShell upload/run. It plans and applies the requested correction using the bootstrap’s saved-plan checks, then verifies installed policies/attachments. Policy definitions and user attachments both have `prevent_destroy`; normal `down` uses a different Terraform root. The script is a snapshot of the prepared correction; regenerate the bundle if installed definitions change before running it.
