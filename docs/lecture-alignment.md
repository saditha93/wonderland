# Teaching material alignment
Page numbers refer to the uploaded PDFs. These are short original summaries, not copied lecture prose. Implementation choices beyond the sources are explicitly engineering proposals.

| Source and pages | Observable topic | Project use / evidence | LO |
|---|---|---|---|
| Lecture 1 pp22–30,39 | Consumption, elasticity, self-healing and cloud risks | Temporary infrastructure, cost and lock-in discussion | LO1, LO4 |
| Lecture 2 pp11–17,20–27,31–39 | Cost/control trade-offs; containers; EKS/ECS; instance choices; FaaS cold start | EKS justified by Kubernetes assessment; on-demand demo workers rather than unreliable Spot during viva | LO2, LO4 |
| Lecture 3 pp5–17,18–29 | Block/object/file storage; snapshots; S3 lifecycle and TLS | Encrypted volumes; optional artifact bucket; SQL database selection is our proposal, not attributed to this lecture | LO2, LO3 |
| Lecture 4 pp7–14 | CQRS and when to use it | Separate booking writes and reporting projections, P4 | LO2, LO3 |
| Lecture 4 pp15–20 | Sidecar use cases | Evaluate; use node log collection rather than unnecessary per-pod sidecars | LO2, LO3 |
| Lecture 4 pp21–22 | Service discovery | Kubernetes Services/DNS, P5 | LO3 |
| Lecture 4 pp23–24 | Circuit breaker | Payment breaker/outage tests keep booking pending in P2; broader faults P5 | LO3 |
| Lecture 4 pp25–27 | API gateway | HTTP API routes to private Kubernetes services, P6 | LO2, LO3 |
| Lecture 4 pp29–30 | Log aggregation, CloudWatch example | JSON stdout now; CloudWatch collection later | LO5 |
| Lecture 4 pp31–33 | Push/pull performance metrics | Planned request latency/error/queue-age metrics | LO5 |
| Lecture 4 pp34–35 | Request ID propagation and timing | Validated request ID and request duration now; propagation/spans later | LO5 |
| Lecture 4 pp36–37 | Health checks | Liveness now; catalog/booking PostgreSQL readiness P2; gate/worker dependency probes later | LO3, LO5 |
| Lecture 4 pp39–43 | Blue-green and canary deployments | Plan blue-green selector switch; distinguish from ordinary rolling update | LO3, LO5 |
| Lab 1 pp1–3 | Account, MFA, region/console | Manual account preparation later; no account changes now | LO3 |
| Lab 2 pp1–3 | EC2, SSH, AWS CLI, Lambda | Explain alternatives; CLI preflight later, no mandatory Lambda added | LO2 |
| Lab 3 pp1–3 | AMI/EBS/snapshot and S3 hosting | Cleanup retained snapshots; compare Amplify hosting | LO2, LO4 |
| Lab 5 pp1–3 | Docker CLI, inspect, custom images | Four Dockerfiles and Compose; execution requires Docker | LO2, LO3 |
| Lab 7 pp1–2 | kubectl, Minikube, cluster/dashboard | Local cluster rehearsal P5; lab uses EC2, our local Mac avoids charges | LO3 |
| Lab 8 pp1–2 | Deployment configs, scaling, load balancing | P5 replica/self-heal/discovery demo | LO3 |
| Module outline pp1–3 | LO1 foundation; LO2 offerings; LO3 NFR; LO4 economy; LO5 monitoring/DevOps | Requirements, ADRs, NFR checks, cost estimate, CI/IaC evidence | LO1–LO5 |
| Schedule pp1–4 | Sequence and assessment dates | Planning only; not evidence that missing lectures were read | — |

Schedule p2 calls Docker “Lab 6”; the actual uploaded Docker sheet is “Lab 5”. Use the uploaded sheet title in citations and flag the numbering discrepancy. Some slide diagrams have sparse text and need visual review before being reproduced or interpreted.
