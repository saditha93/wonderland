"""Coordinate the application release after Terraform provisioning."""

import json
from botocore.exceptions import ClientError
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    require_free_plan,
    source_fingerprint,
)


from scripts.aws.runtime import prepare_runtime, create_demo_accounts
from scripts.aws.build import publish_images, install_workloads, publish_websites
from scripts.aws.verification import verify_deployment


def release_application(aws, target_settings, deployment_details):
    require_free_plan(aws)
    # Immutable image tags may only be reused for exactly the same source.
    store = aws.client("s3")
    key = "releases/" + target_settings["release"] + "/source.json"
    fingerprint = source_fingerprint()
    try:
        previous = json.loads(
            store.get_object(Bucket=deployment_details["artifact_bucket"], Key=key)[
                "Body"
            ].read()
        )
        if previous["sha256"] != fingerprint:
            raise GuardError(
                "This release already belongs to different source; select a new release in secrets/simple-cloud/target.json"
            )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            raise
        store.put_object(
            Bucket=deployment_details["artifact_bucket"],
            Key=key,
            Body=json.dumps({"sha256": fingerprint}).encode(),
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
        )
    prepare_runtime(aws, target_settings, deployment_details)
    publish_images(aws, target_settings, deployment_details)
    install_workloads(aws, target_settings, deployment_details)
    publish_websites(aws, target_settings, deployment_details)
    create_demo_accounts(aws, target_settings, deployment_details)
    verify_deployment(aws, target_settings, deployment_details)
