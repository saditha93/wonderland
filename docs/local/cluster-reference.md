# Phase 5 local Kubernetes guide

This environment is separate from the native Phase 4 app/database. Native frontend uses port 5173; the Kubernetes gateway is forwarded on **5180** for visitors and **5181** for administration. Kubernetes demo bookings belong to this cluster's database and do not appear in native Metabase, which remains connected to the native database. Phase 5 validates reporting through the cluster's own reporting API and SQL reconciliation. It does not move Metabase to Kubernetes or connect AWS.

## Prerequisites and scope

macOS ARM64; Homebrew; Python virtual environment/development dependencies; 16 GB host memory. Colima runs a named VM with 4 CPUs, 6 GiB memory and a 30 GiB data disk. Minikube receives 3 CPUs and 4096 MiB in that VM. Initial downloads/builds require internet access and disk space. Local storage/images continue using disk after the cluster stops. No recurring cloud charge is involved.

Official references: [Colima setup](https://colima.run/docs/getting-started/), [Minikube Docker driver](https://minikube.sigs.k8s.io/docs/reference/drivers/docker/), [Kubernetes HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/). CPU utilization scaling requires CPU requests and a working metrics-server; a manifest alone is not proof of scaling.

## Start, build, deploy and open

```bash
HOMEBREW_NO_AUTO_UPDATE=1 brew install colima docker docker-buildx minikube kubernetes-cli
colima start --profile wonderland --cpu 4 --memory 6 --disk 30 --runtime docker --vm-type vz
.venv/bin/python scripts/local-kubernetes.py start
.venv/bin/python scripts/local-kubernetes.py build
.venv/bin/python scripts/local-kubernetes.py deploy
.venv/bin/python scripts/local-kubernetes.py verify
.venv/bin/python scripts/local-kubernetes.py forward
```

The start helper pins Kubernetes v1.37.0 and enables metrics-server. Its environment explicitly selects Docker context `colima-wonderland`. Colima initially selects that Docker context globally; subsequent project commands select it explicitly. Homebrew installs Docker plugins under `/opt/homebrew/lib/docker/cli-plugins`; register that directory using Homebrew’s printed instructions, or link the plugins into `~/.docker/cli-plugins` without replacing existing files. This machine uses such links for Buildx and Compose. Default kubectl configuration is not used. A dedicated kubeconfig and the named Minikube profile are checked before mutations; non-local endpoints are rejected. The helper does not inspect or contact AWS credentials.

Open [the visitor app](http://localhost:5180) and [the separate administrator app](http://localhost:5181). The forward helper exposes both ports. After an upgrade, build/deploy again to include both app artifacts and the local login configuration.

Setup creates private `secrets/kubernetes.accounts.json`. Open it locally for passwords. Use `visitor@wonderland.local` in the visitor app, `admin@wonderland.local` in the administrator app, and `kube-test@wonderland.local` in the visitor app to inspect the `phase5-demo-visitor` smoke history. Native credentials do not work here. Both apps have sign-in forms; sessions remain in memory and clear on refresh. No token copying is required.

In another terminal, while forwarding:

```bash
.venv/bin/python scripts/checks/cluster.py
.venv/bin/python scripts/demo-kubernetes.py self-heal
.venv/bin/python scripts/demo-kubernetes.py blue-green
.venv/bin/python scripts/demo-kubernetes.py recovery
.venv/bin/python scripts/demo-kubernetes.py readiness
.venv/bin/python scripts/demo-kubernetes.py autoscale
```

The smoke scenario uses a local simulated payment and creates a labelled demo Family booking, full-party arrival and two-rider event. Its documented development-only SQL adjustment models a booking made earlier for today's visit, while payment still follows the verified simulator path. Repeating a same-day scenario reuses identifiers. Different scenarios intentionally create separate demo records. Do not treat these as real visitor statistics.

## Demonstrations and expected observations

| Demonstration | Evidence collected by the script |
|---|---|
| Service discovery/business integration | Browser-style HTTP through nginx → ClusterIP APIs; gate's catalog lookup resolves internal service DNS; signed payment/ticket/check-in/ride and report reconciliation |
| Self-healing | Delete one blue catalog pod; observe a new pod UID ready; catalog requests continue through another replica |
| Blue-green | Bring up separate green catalog Deployment; switch stable Service selector; observe version metadata 0.5.1; restore blue 0.5.0 and scale green to zero |
| Analytics failure isolation | Scale only worker to zero; booking/gate/ride operations still succeed; durable outbox backlog persists; restart worker and reconcile without double-counting |
| Readiness vs liveness | Stop the cluster's PostgreSQL pod; API live remains 200, ready becomes 503, unready Service endpoints disappear; restore PostgreSQL and verify booking count persisted |
| CPU autoscaling | 16 concurrent HTTP clients for 100 seconds; observe HPA grow catalog from 2 to 3 ready replicas; wait for scale-down after load stops |

The green image tag refers to the **same domain code/artifact** as blue; its explicit `APP_VERSION=0.5.1` is release metadata for demonstrating routing and rollback. This is not a claim of a functional code upgrade, schema migration, canary rollout or weighted traffic routing. HPA targets blue only; green uses two fixed replicas during the release demonstration. The scripts restore selectors, PostgreSQL and worker replicas in `finally` blocks. Run one demonstration at a time. Hard process termination can bypass cleanup; inspect the named cluster before resuming.

Autoscale load is bounded to the local catalog endpoint. The script reports success/failure counts and fails if scaling is not observed. It does not add an artificial CPU-burn route. Load results are local observations, not production capacity/SLA claims. HPA CPU metrics can take time to initialize; wait until `verify` shows `kubectl top` data before the demo. A single-node cluster cannot prove node high availability, multi-AZ failover or cluster autoscaling.

## Security, persistence and recovery

API containers run as non-root with read-only root filesystems, dropped capabilities, RuntimeDefault seccomp and no mounted Kubernetes API token. Temporary paths use emptyDir. PostgreSQL uses its image's unprivileged UID/GID 70 and a 2 GiB PVC, with writable runtime paths supplied separately. The static nginx image runs as UID 101. API resource requests/limits and probes are declared. API preStop hooks allow five seconds for endpoint removal before SIGTERM; the process then drains in-flight requests within its termination grace period. No secret values are committed or passed as command-line arguments. The migrator alone gets the owner URL and role provisioning passwords; API roles stay isolated.

Kubernetes Secrets are not encryption by themselves. This local single-node cluster is not a production security boundary: host/cluster administrators can inspect secrets, local etcd/storage are not claimed encrypted, and no NetworkPolicy/TLS/cloud IAM is implemented in Phase 5. AWS auth must use the later approved overlay and managed-secret approach; local identity configuration is prohibited outside local/test by application settings. The nginx proxy is a local entry point, not AWS API Gateway.

A successful versioned migration Job is reused on repeated deploys. New migration versions need a new Job identity or an explicitly reviewed rerun; migrations themselves are repeatable and advisory-locked. Deployment reapplies the intended blue baseline; do not reapply during a green switch. Stop the local cluster without deleting data:

```bash
# Stop port-forward with Ctrl-C first.
.venv/bin/python scripts/local-kubernetes.py stop
colima stop --profile wonderland
```

Stopping Colima does not remove its images or persistent demo storage. The native PostgreSQL cluster is independent; stopping it uses `scripts/local/database.py stop`. Neither deployment nor stop helper deletes PVCs/namespaces/clusters. No destructive cleanup is required for Phase 5. Back up needed demo data before any future deliberate reset.
