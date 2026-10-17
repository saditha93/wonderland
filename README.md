# Wonderland

Cloud Computing assignment **SE6020 · Semester 3**

**T.M.S.U Tennakoon · MS21930386**

Wonderland is a theme park booking MVP with separate React visitor and administrator websites. Four Python microservices handle attractions, bookings and payments, gate admission and rides, and analytics.

Repository: [github.com/saditha93/wonderland](https://github.com/saditha93/wonderland)

## Architecture

```text
Visitor and admin websites on Amplify → Cognito authentication
Websites → API Gateway → protected HTTPS proxy → Minikube Ingress
        → attractions / booking / gate and rides / analytics
        → PostgreSQL schemas and outboxes → SQS → reporting → Metabase
```

The main AWS deployment uses one 8 GiB Ubuntu EC2 server with Minikube, kubectl and the built-in Ingress add-on. ECR stores Docker images, a private S3 bucket stores release artifacts, Secrets Manager holds runtime material and CloudWatch receives application logs. PostgreSQL and Metabase run inside Kubernetes. This is a single-host demonstration, not a highly available production cluster.

## Run the AWS demonstration

Run from the project root after completing the private setup in [deployment.md](docs/deployment.md).

```bash
./demo.sh test              # Regression tests and both frontend builds
./demo.sh terraform-check   # Offline Terraform checks; creates no cloud resources
./demo.sh up                # Plan, create AWS resources and release the application
./demo.sh status            # Actual visitor, admin and API URLs plus SSH command
./demo.sh check             # Hosted APIs, authorization and Metabase SQL checks
./demo.sh monitor           # Private Metabase tunnel; keep this terminal open
```

Visit **http://127.0.0.1:3001** while the monitoring tunnel runs. Cloud accounts are stored privately in `secrets/simple-cloud/accounts.json`; Metabase credentials are in `secrets/metabase-ec2.json`. Do not include those files in screenshots or submissions. The URLs change after infrastructure is recreated.

Follow [the demo guide](docs/demo.md) for visitor booking → Stripe sandbox payment → gate admission → ride recording → reports. After the demonstration, close the tunnel with Ctrl+C and run:

```bash
./demo.sh down              # Verify a fresh backup, destroy and audit
./demo.sh audit             # Confirm no active demo resources remain
```

Keep Terminal open until completion. Stopping Minikube or terminating EC2 alone does not remove the whole AWS stack. Normal cleanup retains reusable deployment permissions, private configuration, state and backups. AWS resources consume credits; review the cost and plan. Use `./demo.sh plan` or `./demo.sh plan-down` for a preview.

## Essential documentation

| Document | Purpose |
|---|---|
| [Demo guide](docs/demo.md) | Run commands, credentials locations, browser steps and expected results |
| [Deployment guide](docs/deployment.md) | One-time setup, Terraform, SSH, server inspection and recovery |
| [Viva guide](docs/viva.md) | Architecture explanation, code map and questions |
| [Assignment summary](docs/assignment/report.md) | Requirements coverage and repository handover |
| [Recorded results](docs/results/aws-rehearsal.md) | Latest observed cloud tests and their limits |

The submission Word report contains the Semester 3 cover, architecture diagrams, implementation screenshots, repository links and test results. The original file is maintained separately from public source. Current local interface captures are labelled separately from the recorded AWS screenshots.

## Verified baseline

The latest recorded Minikube rehearsal was **17 October 2026**: 212 Python tests, both frontend builds, six offline Terraform configurations, 45 AWS resources, four healthy Ingress routes, Stripe sandbox success/decline, concurrent admission, service isolation, restart recovery and all seven Metabase SQL cards. The recorded teardown ended with empty application state and no active demo resources. This historical result does not replace `./demo.sh audit` for today's inventory.

Remote GitHub CI success and examiner repository access still need confirmation. The supplied CI workflow checks the application; automatic GitHub-to-AWS deployment is not implemented. The current release uses server builds and private S3 artifacts.

## Source layout

```text
frontend/src/                visitor, admin, auth and shared UI
services/                    four FastAPI microservices and migrations
wonderland_common/           shared identity, tickets, database and resilience
scripts/aws/                 cloud lifecycle, release, verification and cleanup
infrastructure/aws/          EC2 bootstrap and Minikube installation
infrastructure/kubernetes/   workload manifests and four cloud Ingress rules
infrastructure/terraform/    aws main stack, permissions and optional advanced roots
analytics/                   Metabase dashboard and seven SQL queries
tests/                       regression and safety checks
docs/                        essential guides, diagrams and recorded evidence
```

Optional EKS/RDS files remain in `infrastructure/terraform/advanced/`. They are separate from the main Minikube demo and were not deployed in the recorded rehearsal.

## Fresh laptop setup and optional local demo

Use Python 3.12, uv, Node.js 22.12+ and PostgreSQL 17 for local development and tests. On this Mac PostgreSQL binaries are under `/opt/homebrew/opt/postgresql@17/bin`.

```bash
uv venv --python 3.12 .venv  # Only when .venv is missing
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
./demo.sh local             # Visitor localhost:5173; administrator localhost:5174
```

Ctrl+C stops the local apps and preserves data. Cloud deployment additionally needs AWS CLI, Session Manager plugin, Terraform and the private target described in [deployment setup](docs/deployment.md#required-tools-and-private-configuration). The cloud release builds on EC2.

`./demo.sh package` creates a source-only ZIP in `tmp/handover/`. `.env`, `secrets/`, Terraform state, private backups and generated dependencies must stay out of the repository and submission bundle. `./demo.sh help` lists commands; `cloud.sh` exposes advanced recovery operations.
