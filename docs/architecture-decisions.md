# Architecture decision records
Status: accepted as local design baseline; cloud execution awaits later explicit approval.

## ADR-001 — PostgreSQL and temporary RDS PostgreSQL
| Criterion | PostgreSQL / RDS | DynamoDB |
|---|---|---|
| Booking consistency | Transactions, unique constraints and row locks support confirmation/check-in | Conditional writes and transactions possible; requires access-pattern design |
| Metabase reporting | Direct SQL, time buckets, joins and aggregations | Needs export/stream transformation into a supported SQL store; not a direct drop-in |
| Local reproducibility | Same engine in Docker and RDS; migrations and deterministic seeds | Local emulator differs from managed integration; reporting store also needed |
| Cost | Local development free of AWS usage; RDS accrues instance/storage/backup charges | On-demand helps intermittent traffic; reporting pipeline adds storage/compute cost |
| Operations | Schema migrations, pool sizing and database failure domain | IAM/access patterns/index design plus analytics transformation operations |

Decision: PostgreSQL 17 locally; managed, private, encrypted, Single-AZ RDS PostgreSQL for short demos. Select supported exact engine patch and instance after regional pricing review in P6. Single-AZ is a cost trade-off, not production HA. Use repeatable migrations/seeds; demo data is disposable. Optional retained snapshots require explicit retention and ongoing-cost decision. Do not maintain always-on RDS. DynamoDB would make sense for independently scaled key access, but adds reporting complexity disproportionate to this assessment.

## ADR-002 — Four small services, shared instance with owned schemas
Keeps separate deployments and service isolation without an expensive database per service. Accept common DB outage and migration coordination; prohibit cross-schema business writes. Shared middleware is duplicated in tiny skeletons to preserve independent images; extract a versioned common package only when duplication grows.

## ADR-003 — EKS, with local Minikube first
Kubernetes is mandatory (assignment p4); EKS matches requested AWS direction and Labs 7/8. ECS would reduce cluster management but would not demonstrate Kubernetes. EKS is chargeable even without workloads. Lambda remains an alternative to explain, not an extra service to implement.

## ADR-004 — Terraform with staged lifecycle
Honor user's Terraform preference. Assignment p3 Task 1 names CloudFormation for AWS, while p4 Task 8 allows either. Lecturer clarification remains open. Separate encrypted, versioned state backend for bootstrap/persistent and demo; state locking and restricted IAM; no secrets/state in Git. Bootstrap initially requires a carefully controlled local state, then backend migration. Never destroy the backend as part of demo cleanup.

Persistent: state bucket/configuration, bounded ECR repositories, optional Cognito users and Amplify app configuration (each explicitly costed). Temporary: VPC, EKS/nodes/EBS, internal ALB, VPC link/API, RDS, SQS/DLQ, temporary secrets/log groups and workloads. Persistent modules must not reference demo resources. Amplify API URLs/config must be refreshed per deployment; do not leave stale endpoints.

Provision persistent state -> plan and approve temporary infrastructure -> provision network/cluster/DB/queue -> publish images -> configure kube access/controller/IAM -> create workload LB -> resolve listener and provision API Gateway integration -> migrate/seed -> build/update Amplify environment -> verify. Use distinct demo core and edge stages/states if LB ownership requires it, never cyclic Terraform/Kubernetes dependencies. Cleanup reverses edge references, deletes Ingress/Services, waits for controller removal of ALB/ENIs, then destroys core; audit residual costs and retained artifacts. Phase 6 scripts must implement actual operations and refuse unapproved changes; no pretend-success scripts are provided now.

## ADR-005 — Outbox + at-least-once queue + idempotent reporting
Avoid dual-write loss. Queue/projection lag is acceptable for dashboards, not for confirming payment. Deduplication and durable outbox need explicit database constraints and crash tests in P4.

## ADR-006 — Authentication and payment deferred, fail closed
No mock login or permissive admin endpoint in foundation. Cognito and Stripe test mode integrate later. Tests may inject identity, but insecure development identity must never be deployable in AWS. Never put secrets in Vite environment variables (they are public build output).

## ADR-007 — Blue-green demonstration, no sidecar initially
Use two versions and controlled Service selector switch with rollback after readiness verification in P5. Requires spare capacity; scale down afterward. Canary gradually shifts a subset of traffic and needs meaningful routing/metrics; do not call an ordinary rolling update a canary. Node-level log agent is simpler than a sidecar for these uniform Python services. Revisit sidecar only for measured TLS/proxy needs.
