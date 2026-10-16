# Main AWS deployment tools

Run `./cloud.sh help` from the project root. The normal sequence is `up`, `status`, `verify`, `monitoring`, `down`, then `cleanup-check`.

| File | Responsibility |
|---|---|
| `cli.py` | Read the target, check identity, review/apply Terraform plans and route commands |
| `release.py` | Show the release sequence in one short function |
| `runtime.py` | Prepare Stripe, runtime material and Cognito demo identities |
| `build.py` | Coordinate server image/site builds and workload installation |
| `remote.py` | Run bounded SSM operations and keep diagnostics private |
| `verification.py` | Verify the platform/SQL cards and open the monitoring tunnel |
| `cleanup.py` | Back up first, destroy the reviewed resources, then audit inventory |
| `credentials.py` | Load credentials privately and define safe configuration errors |
| `policies.py` | Generate the bounded deployment/runtime IAM policies |
| `workload_templates.py` | Shared Kubernetes workload and TLS templates |
| `workloads.py` | Adapt those templates to the selected single-server deployment |
| `image_builder.py` | Build and publish containers on EC2 |
| `site_builder.py` | Build visitor/admin websites on EC2 and upload to Amplify |

Server programs read short-lived/private build information from Secrets Manager. Keys never enter the public source bundle. Terraform state and backup paths remain under `secrets/simple-cloud/` to preserve existing private data despite the source reorganization.
