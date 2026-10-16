# Phase 5 outcome — local Kubernetes

The user authorized Phase 5 after Phase 4. Implementation and live local verification cover Minikube deployment, service discovery, readiness/liveness, self-healing, persistent storage, analytics outage recovery and blue-green selector switching. CPU HPA scale-up and scale-down are verified. Stop before Phase 6 (Terraform and AWS lifecycle implementation).

## Objectives, files and steps

Deploy the existing application as real containers in a named local Kubernetes cluster, keep native data separate, demonstrate recovery and replica management, and preserve truthful evidence.

- `infrastructure/kubernetes/base/`: Namespace, API Deployments/Services, static frontend and CPU HPA.
- `infrastructure/kubernetes/local/`: ConfigMap, PostgreSQL StatefulSet/PVC and migration Job, local Kustomize overlay.
- `infrastructure/kubernetes/demos/attractions-green.yaml`: separate green release Deployment.
- `frontend/Dockerfile.kubernetes`, `frontend/nginx.conf`: production static frontend and internal API proxy, separate from Vite's development container.
- `scripts/local-kubernetes.py`: guarded local start/build/ordered deploy/status/port-forward/stop commands, dedicated kubeconfig and secret provisioning on stdin.
- `scripts/checks/cluster.py`, `scripts/demo-kubernetes.py`: actual business integration, failure/release/load demonstrations and reconciliation.
- `tests/test_kubernetes.py`, `tests/conftest.py`: deployment safety contracts, cloud-context rejection and sanitized unavailable-database preflight.
- `.github/workflows/ci.yml`: adds static Kubernetes frontend image build; remote execution remains unverified.
- `docs/local/cluster-reference.md`, phase outcome, architecture/requirements/validation documents: reproducible commands, evidence and limits.

Install local tooling → start named Colima VM/Minikube → build/load images → provision private secrets → start PostgreSQL → migrate/seed/grant roles → deploy APIs/frontend → forward local gateway → run smoke and bounded fault/load demonstrations. No cloud resource, AWS account connection, payment-provider request, commit or push was performed.

## Commands and acceptance criteria

See [the complete local guide](../../local/cluster-reference.md). Main commands, after tooling installation:

```bash
colima start --profile wonderland --cpu 4 --memory 6 --disk 30 --runtime docker --vm-type vz
.venv/bin/python scripts/local-kubernetes.py start
.venv/bin/python scripts/local-kubernetes.py build
.venv/bin/python scripts/local-kubernetes.py deploy
.venv/bin/python scripts/local-kubernetes.py verify
.venv/bin/python scripts/local-kubernetes.py forward
# Another terminal:
.venv/bin/python scripts/checks/cluster.py
.venv/bin/python scripts/demo-kubernetes.py self-heal
.venv/bin/python scripts/demo-kubernetes.py blue-green
.venv/bin/python scripts/demo-kubernetes.py recovery
.venv/bin/python scripts/demo-kubernetes.py readiness
.venv/bin/python scripts/demo-kubernetes.py autoscale
```

Accept when all workloads are ready, migration completed, persistent volume bound, the gateway exercises actual APIs and internal DNS, reporting reconciles against stored operations, replacement/recovery is observed, green/blue routing changes are verified by returned version, and CPU HPA changes actual replicas under bounded HTTP load. A YAML manifest or manual replica change alone is not proof of autoscaling.

## Actual evidence — 14 October 2026

- Installed local Colima 0.10.3, Minikube 1.39.0, kubectl 1.37.1, Docker CLI 29.9.0, Buildx 0.38.0 and Compose 5.6.0. Named Colima Docker daemon reports 29.5.2. Kubernetes node is v1.37.0 with metrics-server v0.9.0. Homebrew warned about an unrelated untrusted tap; no trust was granted or changes made to that tap.
- All six application/migration image builds succeeded and were loaded into Minikube; the green catalog tag uses the same domain artifact. PostgreSQL 17.11-alpine uses a separate 2 GiB Bound PVC.
- Migration Job completed; two catalog and two booking replicas, one gate, one analytics worker, one static frontend and PostgreSQL became ready. All API readiness endpoints responded successfully through the forwarded gateway.
- Real cluster smoke passed: stored tier → Family booking → local verified simulated payment → RSA ticket → four-guest gate arrival → two-rider event and duplicate retry → owned history → reporting/source reconciliation.
- Deleted a catalog pod; a replacement UID became ready; 20/20 catalog requests succeeded during replacement.
- Green became ready; Service selector switched; version metadata 0.5.1 and catalog response were verified. Rollback restored blue 0.5.0; green was scaled to zero. Domain code is identical: this proves routing/rollback, not a functional feature upgrade or canary.
- Worker scaled to zero; new booking, gate and ride operations succeeded and three unpublished events remained durable. Worker restart drained them; replay of the same scenario did not create duplicate arrivals/rides/purchases, and all source/report totals reconciled.
- PostgreSQL scaled to zero: catalog liveness 200 and readiness 503; unready catalog endpoints were removed; frontend process health stayed 200. PostgreSQL restart restored API readiness and retained booking count on the PVC.
- CPU HPA repeat demonstration: 49,693 successful catalog requests, zero failures, 16 concurrent clients over 100 seconds; catalog scaled from two to three ready replicas, then returned to two after traffic stopped. The initial sampler stopped before the delayed controller response; it failed rather than claiming success. A bounded post-load observation window was added, and the repeat passed.
- Server-side dry run accepted every local Kustomize resource. Final isolated demo totals reconcile: two purchases, 28,000 USD cents, eight arriving guests and four riders.
- 105 automated tests passed, no skips; nine Phase 5 safety/security tests plus the existing 96 regression tests. One upstream Starlette TestClient deprecation warning remains. TypeScript/Vite production build passed. Docker Compose configuration validates successfully; Compose runtime was not exercised separately from Minikube.

The first regression attempt found the native PostgreSQL process stopped. Its normal connection traceback exposed a local owner password. That password was rotated in the native database and its two owner URLs/private password file, without changing stored data or service/ticket keys. The test fixture now fails with a sanitized preflight message, verified by a subprocess test that checks a password sentinel never appears. The rerun passed. The first frontend container build also exposed a Dockerfile path error in the helper; it was corrected, and the complete image build/deployment then passed. Failed attempts are not counted as successful verification.

## Manual review and remaining risks

Open [the Kubernetes app](http://localhost:5180), generate an administrator token with `scripts/local-token.py --env-file secrets/kubernetes.env --subject demo-admin --role admin`, then review Administrator/Analytics. Keep tokens and `secrets/` files private. These local Kubernetes identities/data differ from native mode. Native Metabase remains a separate Phase 4 installation and is not connected to this cluster's database; cluster reporting is verified through its API and SQL.

Interactive UI/chart review remains pending after the prior browser policy rejection. This single-node local cluster does not prove node or multi-AZ availability. PostgreSQL remains a common failure domain. Local identity, unencrypted local Secret/PVC storage and HTTP proxying are not a production security model; cloud TLS/IAM/Cognito/API Gateway/SQS remain later approved work. No NetworkPolicy, cloud alerts, archival, database backup/restore, cluster autoscaler or real cloud integration is claimed. Remote CI is configured, not run. Images are version-tagged local builds from locked Python/npm dependencies; upstream base tags can drift on a fresh build. Record image IDs for the viva.

The named cluster and port-forward are left running for review. Stop forwarding with Ctrl-C, then use `scripts/local-kubernetes.py stop` and `colima stop --profile wonderland` to release VM memory while preserving demo data/images. No PVC/namespace/cluster deletion is performed. Phase 6 starts only after the Phase 5 outcome is reviewed; AWS access/apply/destroy still requires its separate explicit approval.
