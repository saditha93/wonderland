# Main AWS demo root

Use `./demo.sh up` and `./demo.sh down` from the project root. The controller prepares private inputs, reviews saved plans, builds/releases the application, backs up the database before deletion and audits remaining resources.

The `.tf` files form **one configuration and one state**. They are split by purpose: versions/providers/inputs, network, server, storage, identity, hosting, gateway, monitoring and outputs. Terraform resource addresses are unchanged from the tested deployment.

State stays in ignored `secrets/simple-cloud/terraform.tfstate`; the folder name is retained to preserve existing private data. Never publish that file or run an unreviewed apply/destroy from this folder.

- `../permissions/`: one-time administrator setup, retained between demos.
- `../advanced/`: optional EKS/RDS alternatives.
- `tests/`: mocked plans for offline checks, with no live AWS creation.

The actual flow and trade-offs are explained in [the deployment guide](../../../docs/deployment.md) and [the viva guide](../../../docs/viva.md).
