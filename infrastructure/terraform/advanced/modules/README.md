# Local Terraform modules

`network/` creates the dedicated VPC, two public worker subnets, two private DB/ALB subnets and public egress routing. `queue/` creates encrypted standard SQS/DLQ with a three-receive redrive policy, scoped redrive allow policy and TLS-only main queue access. Root/provider versions are pinned; no remote module dependency floats. Offline mocked plan tests exercise the roots. No AWS operation has been run.
