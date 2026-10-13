# Cost management baseline
No cloud resources created and no AWS account contacted. Public pricing/documentation checked 13 October 2026; refresh for selected region before deployment. No Free Tier/credits assumed in the estimate. Account age, credit balance, region, traffic and retention are unknown.

AWS lists EKS standard support at $0.10/cluster-hour; extended support costs more. Use a supported version and avoid EKS Auto Mode until separately costed. Public IPv4 is $0.005/address-hour. These are verified public rates; all other figures below are planning allowances, not region-specific quotes.

Sources: [EKS pricing](https://aws.amazon.com/eks/pricing/), [VPC pricing](https://aws.amazon.com/vpc/pricing/), [RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/), [Free Tier eligibility](https://aws.amazon.com/free/). RDS bills instance/storage/backup independently; Free Tier eligibility must be checked against the actual account and current offer.

| Item | Assumption | Four-hour rehearsal | 24-hour accidental runtime |
|---|---|---:|---:|
| EKS standard control plane | $0.10/hour | $0.40 | $2.40 |
| Two workers | Allow $0.10–0.25/hour combined; size after local profiling | $0.40–1.00 | $2.40–6.00 |
| Two public worker IPv4 addresses | 2 × $0.005/hour | $0.04 | $0.24 |
| Internal ALB | Allow $0.03–0.06/hour plus usage | $0.12–0.24 | $0.72–1.44 |
| Temporary Single-AZ RDS | Allow $0.03–0.08/hour compute; storage separate | $0.12–0.32 | $0.72–1.92 |
| EBS/RDS storage, ECR, logs, secrets, API, queue, hosting and transfer | Placeholder reserve, must replace with calculator | $1–3 | $1–5 |
| Planning total | Gross, excludes tax and unusual usage | $2.08–5.00 | $7.48–17.00 |

Not a spending cap or an account quote. Rehearsal wall time includes provisioning and teardown, not only demonstration time. RDS minimum billing periods and retained storage can exceed a simple runtime calculation. Budget for multiple rehearsals. A continuously running EKS control plane alone is about $73 per 730-hour month, before nodes or any other service.

Avoid NAT in the proposed limited demo topology; if private workers are chosen, quote NAT hourly/data processing/IPv4 or all required VPC endpoints (ECR API/DKR, S3, STS, SQS, logging, etc.) and routes. Neither NAT nor interface endpoints are implicitly free. Internal ALB avoids public LB IPv4 but still incurs LB and usage fees. Public egress workers have no internet ingress, scoped security groups and encrypted volumes; production private workers are a separate trade-off.

Persistent state/ECR/log retention creates ongoing cost even after demo teardown. Bound image count, log retention and artifact retention. RDS is temporary and seeded; retained snapshots/backups are optional with explicit cost approval. Cognito/Amplify reuse and storage/bandwidth must be evaluated separately. A stopped database is not the same as removed storage.

Before any apply: choose account/region, inspect non-root identity, refresh AWS Pricing Calculator, list resources and retention, show saved Terraform plan and estimate, request explicit approval for that exact plan. Do not modify budgets or billing settings without approval. Alerting is useful but is not a hard spending limit. Before destroy: show target and destruction plan, obtain explicit approval, detach edge integrations and remove controller-managed LBs first. After destroy: audit clusters/nodes, RDS/backups, LB/ENIs/IPs, EBS, NAT/endpoints, queues, secrets, log groups, ECR and retained persistent state. Report unresolved billable resources.
