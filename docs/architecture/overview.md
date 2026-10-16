# Selected architecture

The main demonstration runs in AWS using one 8 GiB EC2 server with K3s, PostgreSQL and Metabase. Two Amplify websites provide separate visitor and administrator entry points. Cognito supplies identity. API Gateway routes/throttles requests to a verified HTTPS NGINX origin; each service validates its own access token, role and ownership rules.

See [the current system diagram](../diagrams/system.mmd), [the report](../assignment/report.md) and [the code map](../code-guide.md).

| Component | Responsibility | Reason |
|---|---|---|
| Visitor/admin React sites | Customer flow and park operations | Separate entry points with reusable authentication/API helpers |
| Attractions API | Catalogue, suitability and retirement | Independent catalogue responsibility |
| Booking API | Profiles, tiers, stored prices, checkout and ticket issuance | Keep financial confirmation and price snapshots together |
| Gate/ride API | Admission, duplicate rejection and ride history | Verify signed tickets independently of booking availability |
| Analytics worker | Outbox/queue processing and reporting facts | Business writes remain durable while reporting is delayed |
| PostgreSQL | Separate schemas and restricted service roles | Simple persistent storage with explicit ownership boundaries |
| Metabase | Seven SQL cards using a read-only BI login | Explainable reports backed by actual operational events |
| SQS | Durable event transport | Retry delivery without inserting duplicate facts |
| Terraform/release controller | Resource lifecycle, builds, migration and hosting | Reproducible setup plus reviewed teardown/backup |

The server is one shared trust and failure domain. PostgreSQL is self-managed on encrypted EBS. Pod replicas, probes and HPA improve workload recovery/scaling; they do not provide multi-node/database high availability or automatically reduce the EC2 bill. Metabase is reached privately through SSM; database/Kubernetes/SSH ports are not publicly opened for convenience.

The earlier EKS/RDS proposal remains [optional reference material](../advanced/eks-architecture.md). Its VPC-link/internal-ALB/RDS topology must not be presented as the selected deployed architecture.

The original cloud rehearsal passed the recorded business and reliability checks, then the stack was destroyed. Its [results and limitations](../results/aws-rehearsal.md) are distinct from checks of the reorganized source.
