# Protected state bootstrap

Real AWS provider configuration for a versioned, encrypted, TLS-only, public-blocked S3 state bucket. Local state is used initially. Reviewed `cloud.py migrate-state` writes an ignored S3 backend override and refuses an existing remote state key. The bucket has prevent_destroy and is never a demo-cleanup target. No AWS operation has been run. See [cloud runbook](../../../docs/cloud-runbook.md).
