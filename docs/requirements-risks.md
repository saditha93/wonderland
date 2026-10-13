# Open requirements and delivery risks
| Risk | Evidence / consequence | Resolution / gate |
|---|---|---|
| Deadline conflict | Assignment p1: 11 October 2026; schedule p3: 18 October. Today is 13 October | Confirm Moodle/lecturer deadline immediately; do not assume extension |
| AWS IaC interpretation | Assignment p3 Task 1 names CloudFormation for AWS; p4 Task 8 allows Terraform | Ask lecturer whether Terraform on AWS satisfies both; retain Terraform design pending answer |
| Absence notice conflict | Assignment p4 requires one week; Lecture1 p11 says two days | Use assignment's stricter rule; verify if relevant |
| Missing materials/diagrams | All requested 13 PDFs extracted; some slides mostly images; later lectures/labs not uploaded | Visual diagram review before using diagram content; no claim to missing teachings |
| Lab numbering mismatch | Uploaded Docker is Lab5; schedule p2 calls Docker Lab6 | Cite actual uploaded sheet |
| Time/capacity definitions | No park hours, time-slot capacity, cancellation/refund or revocation policy specified | Agree explicit assumptions before domain implementation; no invented capacity enforcement |
| Gate semantics | Guest arrival totals required; partial group arrival not defined | Initial proposal one check-in for full booked party; confirm before P3 |
| Account/region and credits unknown | Cannot quote account-specific Free Tier or regional total | User chooses region and budget; review estimator before any cloud calls |
| Local runtimes missing | Docker, kubectl, Minikube and Terraform absent; native PostgreSQL 17.11 installed for Phase 2 | Install/start locally; container and cluster acceptance pending |
| TLS/private gateway integration | VPC link, listener ARN, DNS/certificate and pod TLS require ordered setup | Validate in P6 and approved rehearsal; avoid public backend bypass |
| Availability vs budget | One DB and possibly one worker are shared failure domains | Explicitly report demo limitation; two workers for node-failure evidence |
| Live IaC duration | EKS/RDS provisioning is not instantaneous | Timed rehearsals; ask permitted pre-created persistent resources/viva slot duration |
| Cleanup residue | Controllers, ENIs, EBS, snapshots, ECR, logs and IPv4 may remain | Inventory/tag audit after approved destroy; never assume terraform output proves zero bills |
| Academic policy | Individual work; plagiarism zeroes assignment (p4) | Understand every change, cite sources, acknowledge AI/other assistance per SLIIT policy |

## Phase 2 remaining integration risks
- External Stripe test-account checkout/webhook delivery has not been exercised; SDK tests and the local simulator do not prove provider integration.
- Existing checkout URLs are reused; expired-session replacement, refunds, cancellation and ticket revocation require explicit policy/design.
- Local developer identities are not Cognito registration/login. Keep them local/test-only; AWS/auth connections require separate user approval.
- Container images and migrations are configured but not executed in Docker; CI is prepared, not run remotely.
- Domain tests truncate only dedicated *_test databases; keep TEST_DATABASE_URL away from valuable data.
- Shared SQL instance remains a failure domain; outbox publishing, analytics deduplication, gate isolation and Kubernetes evidence remain future phases.
