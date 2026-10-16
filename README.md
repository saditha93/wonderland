# Wonderland

A theme park booking MVP with separate visitor and administrator websites. Four Python services handle attractions, bookings/payments, gate/rides and reporting. The AWS demo runs Kubernetes, PostgreSQL and Metabase on one server, with Amplify, Cognito, API Gateway, ECR and SQS around it.

## Start here

```bash
./demo.sh help
./demo.sh test
./demo.sh terraform-check
```

`test` runs the regression suite and builds both websites. `terraform-check` validates six configurations with mocked providers. Neither creates AWS resources.

For a live demonstration:

```bash
./demo.sh up       # Review the real plan and cost; type UP
./demo.sh status   # Show visitor/admin/API URLs
./demo.sh check    # Check hosting, APIs, access rules and Metabase SQL
./demo.sh monitor  # Private Metabase tunnel; keep this terminal open
```

Use [the demonstration guide](docs/demo.md) for the visitor → payment → gate → ride → reports walkthrough. When finished, close the monitoring tunnel with Ctrl+C and run:

```bash
./demo.sh down     # Review deletions; type DOWN; backup precedes destruction
./demo.sh audit    # Confirm no active demo resources remain
```

Keep Terminal open until commands finish. Stopping or manually terminating EC2 is not the complete cleanup procedure. Deployment permissions, local configuration and private backups remain for the next run. AWS usage consumes credits; `up` displays the reviewed cost before creating resources.

## Understand and present the project

| Guide | Use it for |
|---|---|
| [Demo](docs/demo.md) | Commands, browser steps and expected results |
| [Viva](docs/viva.md) | A short speaking script and answers to likely questions |
| [Code guide](docs/code-guide.md) | Where each responsibility lives and which functions to explain |
| [Deployment](docs/deployment.md) | Terraform, initial permissions and recovery details |
| [Observed AWS results](docs/results/aws-rehearsal.md) | What was actually tested, including limitations |
| [Assignment checklist](docs/assignment/coverage.md) | Remaining report, UI review, CI and submission work |

The live rehearsal completed before this source reorganization. The reorganized source is checked with regression tests, both frontend builds, local startup and offline Terraform tests; it has not yet had another complete AWS deployment. Historical results are not presented as a new live run.

## Folder map

```text
frontend/src/             visitor/, admin/, auth/, shared/
services/                 attractions, booking, gate/ride, analytics
wonderland_common/        shared authentication, database, tickets, resilience
scripts/aws/              main cloud lifecycle and server build tools
scripts/local/            optional laptop demo
scripts/checks/           optional integration scenarios
infrastructure/aws/       server bootstrap and Kubernetes installation
infrastructure/terraform/ aws/ (main), permissions/ (one-time), advanced/ (optional)
analytics/                dashboard and seven SQL queries
tests/                    regression and safety checks
docs/                     current guides, assignment, results and archive
```

The optional EKS/RDS design and historical phase material are retained under `advanced/` and `docs/archive/`; they are not the main viva deployment.

## Fresh laptop setup

Use Python 3.12, uv, Node.js 22.12+ and PostgreSQL 17 for local tests. On this Mac the PostgreSQL binaries are under `/opt/homebrew/opt/postgresql@17/bin`.

```bash
uv venv --python 3.12 .venv
uv pip sync requirements-dev.lock --python .venv/bin/python
npm --prefix frontend ci
```

Create `.venv` only if missing. Cloud deployment additionally needs the AWS CLI, Session Manager plugin, the pinned Terraform binary and the private target configuration; see [deployment setup](docs/deployment.md). Images and websites build on AWS, so local Docker/Node are not required for the cloud build itself.

Optional commands:

```bash
./demo.sh local     # Visitor localhost:5173; admin localhost:5174
./demo.sh package   # Source-only ZIP in tmp/handover/
```

Private credentials, Terraform state and backups stay in ignored `.env`, `secrets/` and `tmp/`. Never submit those directories. `cloud.sh` and `start.sh` remain available for advanced and existing workflows.
