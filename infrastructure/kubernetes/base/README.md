# Wonderland Kubernetes workloads

The shared workload manifests define four APIs, an internal static frontend/API proxy, ClusterIP Services, health probes, bounded resources and a CPU HPA for the blue catalog Deployment. The local overlay supplies local/test auth configuration, generated secrets, PostgreSQL storage and migration Job. This is a Phase 5 local baseline; the AWS overlay is still unimplemented and these manifests must not be applied to a cloud context.

Use `scripts/local-kubernetes.py`, which selects the dedicated kubeconfig and named local context explicitly. API pods do not mount Kubernetes API credentials. Each API receives its own DB login; only booking receives the ticket signing private key. Readiness checks dependencies; liveness checks process health. PostgreSQL is single-node demo storage, not high availability.
