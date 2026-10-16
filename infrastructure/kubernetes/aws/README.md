# AWS workload generation

`scripts/aws/workload_templates.py` renders reviewed EKS manifests from the shared workload baseline plus actual Terraform outputs/private runtime credentials. It replaces local identity/transport/storage with Cognito, TLS, RDS verification, ECR images, SQS/IRSA and private PostgreSQL-backed Metabase. Secret values are applied through stdin and saved only under ignored mode-0600 secrets. Do not apply the local overlay to AWS.

`metrics-server.yaml` is the unmodified [official v0.8.0 release artifact](https://github.com/kubernetes-sigs/metrics-server/releases/tag/v0.8.0), licensed under the [Kubernetes Metrics Server Apache-2.0 license](https://github.com/kubernetes-sigs/metrics-server/blob/v0.8.0/LICENSE). Its actual EKS kubelet certificate trust still requires Phase 7 verification. The ALB chart is pinned to 1.14.1/controller v2.14.1. The log collector is rendered separately for kube-system with pinned AWS for Fluent Bit 2.34.3.20261001, scoped IRSA and read-only API log paths.

Only local schema/render checks were run; no EKS deployment. See [cloud runbook](../../../docs/advanced/eks-runbook.md).
