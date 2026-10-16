# Current validation — Phase 6, 14 October 2026

No AWS account was contacted, no live Terraform plan/apply/destroy ran, and no registry/Git push or payment-provider request occurred. Earlier records remain in validation-phase-1.md through validation-phase-5.md. A mock plan/schema check is not cloud execution evidence.

| Check | Actual evidence | Limit |
|---|---|---|
| Python regression | 118 passed, no skips; 13 Phase 6 tests and 105 earlier tests | One existing Starlette TestClient deprecation warning |
| Terraform formatting/schema | Four pinned roots validate against real AWS provider 6.68.0 with backend disabled | No account credentials or live refresh |
| Terraform mocked plans | Four offline security plans pass | Does not verify resource existence, quotas, IAM permissions, regional availability or costs |
| Approval guards | CLI refuses before creating a session without explicit access; wrong account/root/role denied; matching action/plan hashes required; tamper/drift/persistent destroy rejected | No paid mutation executed |
| TLS | Real local HTTPS request fails without the internal CA and passes with it; cloud URLs/probes/proxy use TLS/RDS verify-full | Actual AWS certificates/traffic remain unverified |
| Cloud workload schemas | Synthetic render passes local Minikube server-side dry run | No cloud apply or reference/permission validation |
| Nginx TLS syntax | Actual nginx syntax check passes with generated ephemeral local certificates | No production routing/load claim |
| Helm | Pinned public ALB chart renders with expected controller image | No EKS chart installation |
| SQS | Real PostgreSQL/offline-client replay tests still pass; poison message does not starve valid batch; remote status/local-control boundaries implemented | Actual IRSA/queue/DLQ/alerts unverified |
| Secret/privacy contracts | No local JWT secret in cloud pods; private ticket only booking; metadata password separate from URI; API log glob excludes vendor/migration/other namespaces | Actual RDS/Metabase/log delivery/redaction still needs AWS verification |
| Images | Analytics and migration images build/import with networking disabled | Actual cloud migration not run |
| Frontend/config | TypeScript/Vite production build and Compose config validate; shell wrappers parse | Interactive UI/chart review and remote CI pending |
| Existing local services | Four readiness endpoints on localhost:5180 return 200 | Phase 5 images/data remain separate from cloud preparation |

See [Phase 6 outcome](phase-6-outcome.md), [cloud runbook](../../advanced/eks-runbook.md) and docs/results/evidence/phase6-2026-10-14.txt. Sequential provider checks resolved local concurrent plugin startup failures. HCL syntax, application-test scoping of the vendored operator manifest, gate CA wiring and SG ownership issues were fixed before the successful final checks. No failed intermediate run is counted as successful evidence. Real cloud execution belongs to Phase 7 after target selection, actual plan/cost review and explicit approval.
