# Temporary API edge

API Gateway HTTP API → private VPC link → actual controller-created ALB HTTPS listener, with verified TLS server name, exact Amplify CORS origin, bounded throttling and sanitized access logs. Listener/SG inputs are discovered after approved workload rollout, breaking the Terraform/Kubernetes dependency cycle. Destroy this stage before removing the Ingress/ALB or core. No AWS operation has been run. See [cloud runbook](../../../../docs/advanced/eks-runbook.md).
