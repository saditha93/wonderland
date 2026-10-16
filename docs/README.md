# Documentation

Start with the current guides:

1. [Run the demo](demo.md): simple commands, browser steps and expected results.
2. [Prepare for the viva](viva.md): speaking sequence and design explanations.
3. [Read the code](code-guide.md): feature folders and important functions.
4. [Deploy and recover](deployment.md): Terraform, permissions and private state.

Supporting material:

| Folder | Contents |
|---|---|
| [assignment](assignment/coverage.md) | Report, requirements and explicit completion gates |
| [architecture](architecture/overview.md) | Design, decisions, patterns, authentication and costs |
| [results](results/aws-rehearsal.md) | Observed AWS/local results and machine-readable evidence |
| [local](local/demo.md) | Optional laptop and local Kubernetes workflows |
| [advanced](advanced/eks-runbook.md) | Optional EKS/RDS alternative |
| [archive](archive/README.md) | Dated phase notes and superseded operating instructions |
| `diagrams/` | Mermaid diagram sources |

Historical evidence describes the source deployed at the time. The reorganization is verified separately with regression checks, frontend builds, local startup and offline Terraform tests. A new complete AWS run of the reorganized source remains a deployment check, not an implied success.

Latest source-layout checks: [reorganization evidence](results/evidence/reorganization.json).
