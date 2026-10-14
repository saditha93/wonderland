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
Keeps separate deployments and service isolation without an expensive database per service. Accept common DB outage and migration coordination; prohibit cross-schema business writes. Phase 1 duplicated tiny middleware; Phase 2 extracts common handling into a shared package copied into each independent image (ADR-009).

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

## ADR-008 — Phase 2 local identity and test payment boundary
The user authorized Phase 2 after reviewing the foundation. To exercise protected business routes without AWS, add an explicit local/test-only signed developer token CLI and a labelled server-signed payment simulator. There is no public identity minting endpoint, no browser-selected administrator privilege and no production bypass. Default auth is disabled/fail-closed; local identities cannot start outside local/test environments. Cognito login/profile remains Phase 3. A Stripe test adapter is implemented with SDK signature tests and mocked network calls; actual provider delivery requires the user's own private test configuration and remains unverified. This refines ADR-006 without claiming managed authentication or real provider verification.

## ADR-009 — Shared middleware package and native PostgreSQL verification
Extract common config/auth/logging/database handling into wonderland_common and copy it into each independent service image. This avoids security middleware drift but creates a shared code/version dependency. Native PostgreSQL 17.11 on loopback permits real transaction/concurrency checks while Docker is unavailable; Compose remains the reproducible container path to verify later. Use separate schemas, API roles and a dedicated destructive-test database. Versioned SQL migrations and seeds preserve stored administrator edits.

## ADR-010 — Independent gate tickets and ownership tags
Phase 3 issues RS256 tickets containing reference/date/party size and a pseudonymous HMAC owner tag. Only booking holds the private signing key; gate uses the public key and tag key to enforce visitor history ownership without cross-schema access or a synchronous booking call. Legacy ref-only/HS256 QR payloads must be re-issued through the confirmed-ticket endpoint. Full-party single admission is an explicit initial policy. No cancellations/refunds exist; adding them requires revocation/freshness design before continuing to trust signed tickets offline. Key rotation and ownership-tag migration are future controlled operations.

## ADR-011 — Cognito code now, actual account verification later
Implement the real SDK and JWT/JWKS verifier, test with generated offline keys, and keep local mode as default. This honors the user's prohibition on AWS account connections before approval. Managed signup/login is not marked externally verified. Application administrator rights come from signed group membership; profiles/signup cannot choose a role. In-memory sessions reduce persistent browser token storage but require sign-in after refresh. Cached JWT verification does not immediately revoke signed tokens after logout/group changes; document TTL and future denylist needs.

## ADR-012 — Gate independence, ride status fail-closed and durable events
Check-in uses only signed ticket plus own visits schema, proven while booking process is down. Ride recording requires prior same-day arrival and a bounded HTTP catalog check protected by a breaker; no ride is recorded when status is unverifiable. The live catalog check can race with subsequent retirement and is not a distributed transaction. Each arrival/ride write and its outbox record commit atomically; worker delivery is Phase 4. Operational totals group by stable IDs rather than mutable labels.

## ADR-013 — Transactional local queue and separate BI permissions
Phase 4 uses a durable reporting.queue table as local transport. Queue insertion and outbox acknowledgment share a PostgreSQL transaction; consumer fact/dedupe/ack also commit together, with SKIP LOCKED concurrency. Invalid events retry with backoff and reach a persisted dead-letter state. This minimizes local dependencies while accepting the shared database failure domain. A separately tested, injected SQS adapter uses send-before-ack and commit-before-delete; real cloud wiring remains deferred. No exactly-once transport claim is made. BI receives SELECT only on aggregate views; the worker can acknowledge only published_at in source outboxes. Local Metabase metadata uses H2 for development; cloud production storage remains a later decision.

## ADR-014 — Named local Minikube, persistent demo storage and honest release evidence
Phase 5 uses a dedicated Colima Docker VM, named Minikube profile and dedicated kubeconfig. Cluster PostgreSQL data/signing keys are separate from native mode. Ordered deployment waits for persistent PostgreSQL and migrations before workloads. Non-root pods use bounded resources, distinct readiness/liveness checks and no API token mount. The local nginx proxy routes to stable ClusterIP Services; it is not AWS API Gateway. HPA targets the blue catalog; green temporarily runs two replicas for an atomic selector switch and rollback. The green release uses identical domain code with distinct version metadata; no feature/canary claim is made. Single-node storage and local Secrets are development trade-offs, not HA or managed encryption.
