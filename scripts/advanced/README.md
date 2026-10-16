# Optional deployment alternatives

These tools support the earlier EKS/RDS assignment design and the historical local-archive upload implementation. They are not part of `./cloud.sh up`.

- `eks.py`: multi-root EKS/RDS lifecycle with its own explicit account/plan approvals.
- `registry_upload.py`: local Docker archive upload reference. The main AWS path builds images on EC2 instead.

The associated optional Terraform roots are under `infrastructure/terraform/advanced/`. Use the main project commands for the viva unless you deliberately choose and review an alternative topology.
