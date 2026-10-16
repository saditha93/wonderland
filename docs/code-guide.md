# Read the code in this order

Start with a responsibility, then follow its calls. The file layout separates the product, infrastructure and optional teaching material.

## Product code

| Responsibility | Main file(s) | Explain in the viva |
|---|---|---|
| Visitor application | `frontend/src/visitor/VisitorApp.tsx`, `navigation.ts`, `AttractionCard.tsx`, `AccountPanel.tsx` | Page state coordinates browsing, booking, checkout, tickets and owned history |
| Administrator application | `frontend/src/admin/AdminApp.tsx`, `AdminPanel.tsx`, `AnalyticsPanel.tsx` | Separate entry point; an admin identity is required before operations appear |
| Authentication | `frontend/src/auth/`, `wonderland_common/auth.py` | Cognito identity and groups; the API still enforces roles and ownership |
| API requests/types | `frontend/src/shared/api.ts` | One HTTP helper handles access tokens, errors and typed responses |
| Attractions | `services/attractions-service/app/routes.py` | Public browsing and protected create/update/retire operations |
| Reservation creation | `services/booking-service/app/reservations.py` | Validate tier/date/guests, snapshot the price and use an idempotency key |
| Booking ownership | `services/booking-service/app/booking_store.py` | `find_owned_booking` restricts a lookup to its owner; `public_booking` limits returned fields |
| Checkout and webhook | `services/booking-service/app/checkout.py`, `payments.py` | Verify Stripe's signature, compare the stored session/amount and confirm exactly once |
| Signed tickets | `services/booking-service/app/tickets.py`, `wonderland_common/tickets.py` | `issue_signed_ticket` signs paid bookings; gate verifies the public key and visit date |
| Pricing/profiles | `services/booking-service/app/pricing.py`, `profiles.py` | Keep administrative pricing separate from visitor profile operations |
| Gate and rides | `services/gate-ride-service/app/routes.py` | Unique check-in, guest/date validation and ride retry deduplication |
| Analytics | `services/analytics-worker/app/pipeline.py`, `sqs_transport.py` | Outbox → queue → idempotent reporting facts |
| Reporting | `analytics/queries/`, `analytics/dashboard.json` | Seven saved SQL queries over a separate read-only BI role |

Each service's `main.py` assembles the app. The booking service's `routes.py` now only combines feature routers; it no longer contains every business operation. Migrations under each service own that service's database schema.

## AWS command path

```text
./demo.sh up
  → cloud.sh
  → scripts/aws/cli.py: up()
  → reviewed Terraform plan/apply
  → scripts/aws/release.py: release_application()
  → runtime preparation, server builds, workload installation, hosting, accounts, checks
```

| File | Important functions | Responsibility |
|---|---|---|
| `scripts/aws/cli.py` | `load_target`, `create_aws_session`, `plan`, `deploy`, `up` | Check the selected account, review the concrete plan and route commands |
| `credentials.py` | `load_credentials` | Read private AWS values without printing them |
| `runtime.py` | `configure_stripe`, `prepare_runtime`, `create_demo_accounts` | Prepare sandbox webhook, runtime material and Cognito demo identities |
| `build.py` | `publish_images`, `install_workloads`, `publish_websites` | Upload verified public source and perform builds/installation on the server |
| `remote.py` | `run_on_server` | Send bounded SSM commands and retain diagnostics privately |
| `verification.py` | `verify_deployment`, `verify_metabase`, `open_monitoring_tunnel` | Check the hosted platform and query the private dashboard |
| `cleanup.py` | `backup`, `plan_down`, `down`, `apply_destroy`, `audit` | Verify backup before reviewed deletion, handle a detached-IP retry and audit leftovers |
| `workloads.py` / `workload_templates.py` | `render` | Render Kubernetes configuration for the selected server |
| `image_builder.py` / `site_builder.py` | `main` | Programs executed on EC2 to build and publish artifacts |
| `infrastructure/aws/node.py` | install/status/backup actions | Configure the server's workloads, TLS and private monitoring forwarder |

Terraform creates AWS resources. The release scripts build images, run migrations and publish application artifacts. Explaining both parts is more accurate than claiming Terraform itself compiles the application.

## Terraform file map

The main root is `infrastructure/terraform/aws/`. Files share one root and one private state; they are not separate deployments.

| File | Purpose |
|---|---|
| `versions.tf` | Pin Terraform/provider versions and the private local backend |
| `providers.tf` | Restrict account/region and define ownership tags |
| `variables.tf` | Explicit inputs and validation |
| `network.tf` | VPC, subnet, routing, firewall and server interface |
| `server.tf` | EC2, encrypted storage settings and public IP association |
| `storage.tf` | Private S3 artifacts, ECR repositories and runtime secret |
| `identity.tf` | Server role/boundary and Cognito users/groups/client configuration |
| `hosting.tf` | Separate visitor/admin Amplify apps |
| `gateway.tf` | HTTP API, routes, origin protection and throttling |
| `monitoring.tf` | Application log group |
| `outputs.tf` | Actual IDs and URLs consumed by the release controller |

Resource addresses were retained during the split to avoid unnecessary replacements. `permissions/` is the separate administrator setup; `advanced/` retains the optional EKS/RDS design. State/backups keep their existing private directory name to avoid an unnecessary data migration.

## What is optional or generated?

- `scripts/local/` and `docs/local/`: laptop rehearsal.
- `scripts/checks/`: integration scenarios; these deliberately generate disposable test records.
- `scripts/advanced/`, `infrastructure/terraform/advanced/`: alternative/reference workflows.
- `docs/archive/`: dated implementation history, not the main operating instructions.
- `.venv`, `node_modules`, `dist*`, `.terraform`, `tmp/`: generated dependencies, caches, logs or binaries.
- `.env` and `secrets/`: private credentials, configuration, Terraform state and backups; retained and excluded from the handover ZIP.

No new generic framework was introduced. Names reflect the business operation or deployment step, and existing authentication, signature, backup and plan guards remain in place.
