# Optional assignment and technical documentation

For the simple app walkthrough, use the [MVP demo guide](demo-guide.md). You do not need the material below to run that demo.

| Topic | Documents |
|---|---|
| Simple infrastructure commands | [Local infrastructure](infrastructure-demo.md) |
| Report and viva | [Project report](project-report.md), [speaking guide](viva-demo.md) |
| Detailed local tests and troubleshooting | [Advanced local testing](advanced-local-testing.md), [development notes](development.md) |
| Requirements and course alignment | [Requirements matrix](requirements-matrix.md), [lecture alignment](lecture-alignment.md), [viva checklist](viva-checklist.md) |
| Architecture | [Architecture](architecture.md), [decisions](architecture-decisions.md), [design patterns](design-patterns.md) |
| Local Kubernetes | [Commands](local-kubernetes.md), [Phase 5 evidence](phase-5-outcome.md) |
| Metabase | [Simple assignment demonstration](metabase-demo.md), [Phase 4 technical evidence](phase-4-outcome.md) |
| AWS preparation | [Cloud runbook](cloud-runbook.md), [Phase 6 evidence](phase-6-outcome.md), [Cognito boundary](cognito-integration.md) |
| Other phase evidence | [Phase 1](validation-phase-1.md), [Phase 2](phase-2-outcome.md), [Phase 3](phase-3-outcome.md), [separate admin app](separate-admin-outcome.md) |
| Report and costs | [Report outline](report-outline.md), [cost management](cost-management.md), [risks](requirements-risks.md) |

The existing Terraform, Kubernetes, CI, queue and Metabase integrations remain available for assessment work. Phase documents record what was verified at that time; the current MVP UI/startup is described in the short guide. Cloud/account operations require the previously agreed approval. No existing data or credentials were removed during MVP simplification.

MVP verification on 15 October 2026: 135 Python tests passed with no skips; both frontend builds passed; the one-command startup/readiness/shutdown check passed. A real local HTTP rehearsal verified password login, today's booking, simulated payment, administrator reference lookup, duplicate check-in denial, ride recording and source/report reconciliation. Interactive browser appearance was not reviewed in this update.

Local closeout on 15 October 2026: **149 tests**, both app builds and **14 infrastructure stages passed**, including 46,964 successful requests/zero failures and HPA 2→3→2. See [current validation](validation.md), [the report](project-report.md), and [actual infrastructure evidence](evidence/local-infrastructure.json). AWS/remote CI still need separate verification.
