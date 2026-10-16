# Current validation — Phase 5, 14 October 2026

Local verification only. No AWS account access, payment-provider request, Terraform apply/destroy, Git commit or push performed. Earlier validation snapshots are in validation-phase-1.md through validation-phase-4.md.

| Check | Actual evidence | Limit |
|---|---|---|
| Automated suite | 105 passed, no skips; nine Kubernetes safety/security tests and 96 existing tests | Dedicated native *_test PostgreSQL; one upstream Starlette TestClient deprecation warning |
| Test failure privacy | Unavailable-DB preflight hides connection details; subprocess password-sentinel test passes; exposed native owner credential rotated | Initial stopped-DB attempt failed and is not counted as successful verification |
| Frontend | TypeScript/Vite production build passed; static nginx image built | Interactive UI review pending after prior browser policy rejection |
| Container runtime | Six application/migration images built and loaded into real Minikube; green catalog tag loaded | Local ARM64 runtime; base image tags can drift |
| Kubernetes schemas | All Kustomize resources accepted by server-side dry run | Local Kubernetes v1.37.0; AWS overlay not implemented |
| Deployment | Migration completed; APIs/frontend/PostgreSQL ready; 2 GiB PVC Bound | Single-node development cluster |
| Business integration | Actual HTTP via static gateway: tiers/booking/simulated payment/RSA ticket/full-party gate/ride dedupe/history/reporting | Local/test auth only; no external payment/Cognito calls |
| Reporting reconciliation | Two purchases / 28,000 cents / eight arriving guests / four riders matched stored operations | Isolated cluster demo data, separate from native Metabase |
| Self-healing | Deleted catalog pod; new UID ready; 20/20 catalog requests succeeded during replacement | Pod replacement, not node/zone HA |
| Blue-green | Green 0.5.1 selected and verified; rollback to blue 0.5.0 verified; green scaled to zero | Same domain artifact, different release metadata; not a functional update/canary |
| Worker outage | Worker at zero; domain operations succeed; three events buffered; restart drains and reconciles | Shared DB remains a failure domain |
| DB readiness/persistence | DB at zero: live 200/ready 503; unready catalog endpoints removed; restore retains booking count | PVC survives pod restart, not backup/restore or node loss |
| Autoscaling | 49,693 requests, zero failures over 100 seconds; HPA 2 → 3 ready → 2 verified | CPU-based local test, maximum three replicas; no production capacity claim |
| Credentials/configuration | Private cluster env/kubeconfig mode 0600; no tracked secrets/tmp/course materials; Compose config validates | Local Secrets/PVC not claimed encrypted; no NetworkPolicy/TLS/cloud IAM |
| Cloud/remote | Not executed | EKS/API Gateway/Cognito/SQS/Terraform/remote CI remain unverified |

See [Phase 5 outcome](phase-5-outcome.md) and [local Kubernetes guide](../../local/cluster-reference.md) for commands and limitations. Stop before Phase 6. The first frontend image build found a helper Dockerfile path error, which was fixed before the successful complete build. The first load sampler stopped before a delayed HPA response; it reported failure rather than a false pass. The monitor now allows a bounded controller delay and checks actual ready replicas, then waits for scale-down.
