# Pattern selection and demonstrations
All rows are designs unless status explicitly says foundation implemented. Lecture 4 pages from uploaded PDF.

| Pattern / pages | Problem and rationale | Implementation / status | Trade-off | Failure scenario and demonstration |
|---|---|---|---|---|
| API Gateway 25–27 | Multiple external service endpoints | HTTP API + VPC link + internal ALB, P6 | Extra hop, cost and lifecycle dependencies | Stop one target; other routes remain accessible |
| Service discovery 21–22 | Pod addresses change | Kubernetes Services/DNS P5; Compose DNS config now | Cluster DNS dependency | Replace pod and resolve stable Service name |
| Circuit breaker 23–24 | Dependency failure cascades | Payment/provider calls P2/P5, not implemented | State per replica, thresholds need tuning | Simulate timeout, open breaker, pending response, half-open recovery |
| Health checks 36–37 | Process can run but be unready | /health, /health/live, /health/ready now; dependency checks future | Current readiness only skeleton initialization | Kill process; later disable DB and observe readiness 503 without liveness restart loop |
| CQRS 7–14 | Reporting queries compete with validated writes | Reporting schema/outbox P4 | Eventual consistency; shared DB remains | Pause worker, book, then recover report lag |
| Log aggregation 29–30 | Logs spread across replicas | JSON stdout now; CloudWatch collector P6 | Ingestion and retention cost | Search one request ID across services later |
| Metrics 31–33 | Need latency/errors/queue insight | Request duration log now; metrics export/alerts P5/P6 | Cardinality and collection overhead | Load burst, inspect latency/errors and backlog age |
| Tracing 34–35 | Request crosses services | Safe request ID and timing now; propagation and spans later | Request IDs alone are not complete distributed tracing | Trace booking to webhook/event; provider needs separate correlation |
| Sidecar 15–20 | Add behavior without changing app | Evaluated, deferred; prefer node log agent | Per-pod overhead; possible TLS proxy later | Explain why collector DaemonSet is not a sidecar |
| Blue-green 39 | Controlled update and rollback | Separate version Deployments plus Service selector P5 | Temporary double capacity | Verify green then switch and rollback selector |
| Canary 40–43 | Reduce release blast radius | Documented alternative, not implemented | Weighted routing and metrics required | Explain gradual traffic percentage and abort threshold |
