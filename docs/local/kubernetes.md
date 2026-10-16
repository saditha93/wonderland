# Local infrastructure: three commands

Run these from the project folder. No AWS account is used. First-machine dependencies are listed in [the advanced Kubernetes guide](cluster-reference.md); they are already installed on this Mac.

## Test everything locally

```bash
./start.sh infra-test
```

This one command validates Terraform using offline mocks, starts Colima/Minikube, builds/deploys the real containers and runs the business/recovery/scaling tests. It shows a short progress list and writes the actual results to `docs/results/evidence/local-infrastructure.json`. Allow several minutes, especially for builds and autoscaling.

Tests cover booking/payment/tickets, separate admin login, check-in by reference, ride retries, persisted reports, pod replacement, blue-green rollback, worker backlog recovery, database readiness/persistence and CPU autoscaling.

Close an existing infrastructure/port-forward terminal first: the test starts its own gateway. Run demonstrations sequentially. If a test fails, it records failure and attempts to restore the local baseline. Raw logs stay private in `tmp/infrastructure/`. A failed run is not completion evidence.

## Open the Kubernetes apps

```bash
./start.sh infra
```

Keep this terminal open. It prints private cluster login details and exposes:

- Visitor: http://localhost:5180
- Administrator: http://localhost:5181

Use the same [short app demonstration](demo.md), with these URLs and cluster passwords. Native passwords/data on ports 5173/5174 are separate. Today's booking is enabled for this local demo too. The static gateway is nginx; it is not the actual AWS API Gateway service.

Press Ctrl-C to close the gateway. Infrastructure remains running until the next command.

## Stop the infrastructure

```bash
./start.sh infra-stop
```

Stops the named local cluster and VM. Database volumes, signing keys and images remain saved. It does not delete databases or run Terraform destroy.

## Prepare the handover

```bash
./start.sh package
```

Creates `tmp/handover/wonderland-mvp.zip` and its SHA-256 file. The source archive includes the report, guides, code and optional infrastructure. Credentials, database files, installed dependencies, build output and private course PDFs are excluded.

For app-only testing, use `./start.sh test`. For app-only startup, use `./start.sh`.

## What still needs a real account

Local success verifies the application and Kubernetes behavior. Actual AWS EKS/RDS/SQS/API Gateway, hosted Amplify/Cognito, external Stripe webhook delivery and GitHub CI execution need their own account verification. The original Phase 7 cloud rehearsal is not completed by Minikube or mocked Terraform plans. See the [cloud runbook](../advanced/eks-runbook.md) when you choose to do that work.
