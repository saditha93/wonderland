# Optional assignment and technical documentation

For the simple app walkthrough, use the [MVP demo guide](local/demo.md). You do not need the material below to run that demo.

| Topic | Documents |
|---|---|
| Simple infrastructure commands | [Local infrastructure](local/kubernetes.md) |
| Report and viva | [Project report](assignment/report.md), [speaking guide](viva.md) |
| Detailed local tests and troubleshooting | [Advanced local testing](local/troubleshooting.md), [development notes](development.md) |
| Current assignment readiness | [All rubric areas and completion gates](assignment/coverage.md), [gap review](archive/gap-review.md) |
| Requirements and course alignment | [Requirements matrix](assignment/requirements.md), [lecture alignment](assignment/course-alignment.md), [viva checklist](assignment/viva-checklist.md) |
| Architecture | [Architecture](architecture/overview.md), [decisions](architecture/decisions.md), [design patterns](architecture/patterns.md) |
| Local Kubernetes | [Commands](local/cluster-reference.md), [Phase 5 evidence](archive/phases/phase-5-outcome.md) |
| Metabase | [Simple assignment demonstration](local/monitoring.md), [Phase 4 technical evidence](archive/phases/phase-4-outcome.md) |
| AWS deployment permissions | [Reviewed policies and verification](../infrastructure/iam/README.md) |
| Selected small AWS demo | [Simple cloud commands and live-check checklist](archive/aws-demo-notes.md) |
| First AWS deployment | [Account setup and next steps](advanced/account-setup.md) |
| AWS preparation | [Cloud runbook](advanced/eks-runbook.md), [Phase 6 evidence](archive/phases/phase-6-outcome.md), [Cognito boundary](architecture/authentication.md) |
| Other phase evidence | [Phase 1](archive/phases/validation-phase-1.md), [Phase 2](archive/phases/phase-2-outcome.md), [Phase 3](archive/phases/phase-3-outcome.md), [separate admin app](archive/phases/separate-admin.md) |
| Report and costs | [Report outline](assignment/report-outline.md), [cost management](architecture/costs.md), [risks](assignment/risks.md) |

The existing Terraform, Kubernetes, CI, queue and Metabase integrations remain available for assessment work. Phase documents record what was verified at that time; the current MVP UI/startup is described in the short guide. Cloud/account operations require the previously agreed approval. No existing data or credentials were removed during MVP simplification.

MVP verification on 15 October 2026: 135 Python tests passed with no skips; both frontend builds passed; the one-command startup/readiness/shutdown check passed. A real local HTTP rehearsal verified password login, today's booking, simulated payment, administrator reference lookup, duplicate check-in denial, ride recording and source/report reconciliation. Interactive browser appearance was not reviewed in this update.

Local closeout on 15 October 2026: **149 tests**, both app builds and **14 infrastructure stages passed**, including 46,964 successful requests/zero failures and HPA 2→3→2. See [current validation](results/local-validation.md), [the report](assignment/report.md), and [actual infrastructure evidence](results/evidence/local-infrastructure.json). AWS/remote CI still need separate verification.
