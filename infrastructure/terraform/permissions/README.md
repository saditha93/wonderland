# One-time deployment permissions

This root manages bounded project deployment policies and attachments. It is separate from the disposable application stack so normal `down` does not remove the user's deployment access.

Existing permissions are already installed for this project. For a new account or a reviewed policy change, follow [the administrator setup](../../../docs/deployment.md). The private bundle is prepared by `scripts/aws/prepare_permissions.py` and reviewed/applied through the administrator CloudShell runner.

This root creates no demo server and must not be destroyed as part of the viva cleanup. Its tests use a mocked provider. The runtime server role/boundary and application resources remain managed by the main AWS root.
