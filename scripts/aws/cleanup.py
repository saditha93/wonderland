"""Private backup and explicit destruction of the selected disposable AWS demo."""

import gzip
import hashlib
import json
import os
import signal
import socket
import subprocess
import subprocess
import time
import httpx
from dotenv import dotenv_values, set_key
from botocore.exceptions import ClientError
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    TFROOT,
    write_private_json,
    run_terraform,
    source_fingerprint,
)
from scripts.aws.remote import run_on_server


def backup(aws, target_settings, deployment_details):
    if not (PRIVATE / "runtime.json").exists():
        raise GuardError(
            "Preserve the runtime credentials before backing up the database"
        )
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 31365))
    except OSError:
        raise GuardError("Backup tunnel port 31365 is occupied") from None
    finally:
        probe.close()
    result = run_on_server(
        aws,
        deployment_details,
        [
            "/opt/wonderland/runtime/bin/python /opt/wonderland/source/infrastructure/aws/node.py backup --config /opt/wonderland/source/node-config.json"
        ],
        timeout=300,
        echo=False,
    )
    meta = json.loads(result["StandardOutputContent"].strip())
    if meta.get("database_absent") is True:
        record = {
            "no_database_provisioned": True,
            "instance_id": deployment_details["instance_id"],
            "created_at": int(time.time()),
        }
        write_private_json(PRIVATE / "backup.json", record)
        print(
            "Server check confirmed no database was provisioned; private runtime configuration is preserved."
        )
        return record
    logfile = PRIVATE / "backup-tunnel.log"
    with logfile.open("w") as stream:
        logfile.chmod(0o600)
        process = subprocess.Popen(
            [
                "aws",
                "ssm",
                "start-session",
                "--region",
                target_settings["region"],
                "--target",
                deployment_details["instance_id"],
                "--document-name",
                "AWS-StartPortForwardingSession",
                "--parameters",
                json.dumps({"portNumber": ["8765"], "localPortNumber": ["31365"]}),
            ],
            cwd=ROOT,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
        try:
            body = None
            for _ in range(60):
                if process.poll() is not None:
                    raise GuardError(
                        "Backup tunnel exited; database will not be destroyed"
                    )
                try:
                    response = httpx.get(
                        "http://127.0.0.1:31365" + meta["path"], timeout=30
                    )
                    response.raise_for_status()
                    body = response.content
                    break
                except httpx.HTTPError:
                    time.sleep(2)
            if (
                body is None
                or len(body) != meta["size"]
                or hashlib.sha256(body).hexdigest() != meta["sha256"]
            ):
                raise GuardError(
                    "Backup transfer verification failed; database will not be destroyed"
                )
            if b"PostgreSQL database cluster dump" not in gzip.decompress(body):
                raise GuardError("Invalid database backup; destruction refused")
            path = (
                PRIVATE / "backups" / ("database-" + str(int(time.time())) + ".sql.gz")
            )
            path.parent.mkdir(exist_ok=True, mode=0o700)
            path.write_bytes(body)
            path.chmod(0o600)
            record = {
                "path": str(path),
                "sha256": meta["sha256"],
                "size": len(body),
                "created_at": int(time.time()),
                "instance_id": deployment_details["instance_id"],
            }
            write_private_json(PRIVATE / "backup.json", record)
            print("Verified private database backup:", path)
            return record
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            run_on_server(
                aws,
                deployment_details,
                ["systemctl stop wonderland-backup-transfer"],
                timeout=60,
                echo=False,
            )


def cleanup_override():
    return {
        "resource": {
            "aws_instance": {"demo": {"lifecycle": {"prevent_destroy": False}}},
            "aws_s3_bucket": {
                "artifacts": {
                    "force_destroy": True,
                    "lifecycle": {"prevent_destroy": False},
                }
            },
            "aws_ecr_repository": {"app": {"force_delete": True}},
            "aws_secretsmanager_secret": {"runtime": {"recovery_window_in_days": 0}},
            "aws_cognito_user_pool": {"visitors": {"deletion_protection": "INACTIVE"}},
        }
    }


def state_signature():
    path = PRIVATE / "terraform.tfstate"
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def require_destroy_only(document, allowed=None):
    addresses = set()
    for row in document.get("resource_changes", []):
        actions = row["change"]["actions"]
        if actions not in (["delete"], ["no-op"], ["read"]):
            raise GuardError("Unexpected non-destruction action; refusing cleanup")
        if actions == ["delete"]:
            addresses.add(row["address"])
    if allowed is not None and not addresses.issubset(set(allowed)):
        raise GuardError("Destroy plan includes resources outside the approved scope")
    return sorted(addresses)


def plan_down(aws, target_settings):
    override = TFROOT / "cleanup_override.tf.json"
    if override.exists():
        raise GuardError(
            "An interrupted cleanup override exists; inspect it before planning"
        )
    fingerprint = source_fingerprint()
    write_private_json(override, cleanup_override())
    try:
        path = PRIVATE / "reviewed-destroy.tfplan"
        run_terraform(
            "plan",
            "-destroy",
            "-input=false",
            "-no-color",
            "-var-file=" + str(PRIVATE / "terraform.tfvars.json"),
            "-out=" + str(path),
        )
        path.chmod(0o600)
        addresses = require_destroy_only(
            json.loads(run_terraform("show", "-json", str(path), capture=True).stdout)
        )
        review = {
            "target": target_settings,
            "source_sha256": fingerprint,
            "state_sha256": state_signature(),
            "plan_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "resources": addresses,
            "created_at": int(time.time()),
            "preparation": "Disable only demo deletion protections/force-delete flags; backup before destruction",
        }
        digest = hashlib.sha256(
            json.dumps(review, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        write_private_json(
            PRIVATE / "down-review.json", {"review": review, "approval_sha256": digest}
        )
        print("AWS target:", target_settings["account_id"], target_settings["region"])
        print("Terraform resources to delete:", len(addresses))
        print(
            "Private database backup precedes destruction. Source, state, target and deletion scope are bound to approval."
        )
        print("Apply this teardown: ./cloud.sh down --approve " + digest)
        return digest
    finally:
        override.unlink(missing_ok=True)


def down(aws, target_settings, approved):
    value = json.loads((PRIVATE / "down-review.json").read_text())
    review = value["review"]
    digest = hashlib.sha256(
        json.dumps(review, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path = PRIVATE / "reviewed-destroy.tfplan"
    if (
        approved != digest
        or value["approval_sha256"] != digest
        or hashlib.sha256(path.read_bytes()).hexdigest() != review["plan_sha256"]
    ):
        raise GuardError("Supply the exact teardown approval printed by plan-down")
    if (
        review["target"] != target_settings
        or review["source_sha256"] != source_fingerprint()
        or review["state_sha256"] != state_signature()
        or time.time() - review["created_at"] > 3600
    ):
        raise GuardError(
            "Teardown source/state/target changed or review expired; run plan-down again"
        )
    deployment_details = (
        json.loads((PRIVATE / "deployment.json").read_text())
        if (PRIVATE / "deployment.json").exists()
        else None
    )
    destroy(
        aws,
        target_settings,
        deployment_details,
        "destroy-wonderland-demo",
        review["resources"],
    )


def refresh_state():
    path = PRIVATE / "cleanup-refresh.tfplan"
    run_terraform(
        "plan",
        "-refresh-only",
        "-input=false",
        "-no-color",
        "-var-file=" + str(PRIVATE / "terraform.tfvars.json"),
        "-out=" + str(path),
    )
    path.chmod(0o600)
    document = json.loads(
        run_terraform("show", "-json", str(path), capture=True).stdout
    )
    if any(
        r["change"]["actions"] not in (["no-op"], ["read"])
        for r in document.get("resource_changes", [])
    ):
        raise GuardError("Refresh must not change AWS resources")
    run_terraform("apply", "-input=false", "-no-color", str(path))


def backup_if_present(aws, target_settings, deployment_details):
    if not deployment_details or not (PRIVATE / "runtime.json").exists():
        return
    try:
        reservations = aws.client("ec2").describe_instances(
            InstanceIds=[deployment_details["instance_id"]]
        )["Reservations"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidInstanceID.NotFound":
            raise
        reservations = []
    instances = [
        x
        for r in reservations
        for x in r["Instances"]
        if x["State"]["Name"] not in {"terminated", "shutting-down"}
    ]
    if not instances:
        print(
            "Server is already absent. A new database backup cannot be made; any existing private backup is retained."
        )
        write_private_json(
            PRIVATE / "backup-unavailable.json",
            {
                "instance_id": deployment_details["instance_id"],
                "reason": "Server already removed before teardown",
                "checked_at": int(time.time()),
            },
        )
        return
    if instances[0]["State"]["Name"] != "running":
        raise GuardError(
            "Start the existing server before down so its database can be backed up"
        )
    backup(aws, target_settings, deployment_details)


def destroy_plan(variables, allowed, filename="destroy.tfplan"):
    plan = PRIVATE / filename
    run_terraform(
        "plan", "-destroy", "-input=false", "-no-color", variables, "-out=" + str(plan)
    )
    plan.chmod(0o600)
    document = json.loads(
        run_terraform("show", "-json", str(plan), capture=True).stdout
    )
    return plan, require_destroy_only(document, allowed)


def apply_destroy(aws, target_settings, variables, allowed):
    plan, _ = destroy_plan(variables, allowed)
    try:
        run_terraform("apply", "-input=false", "-no-color", str(plan))
    except subprocess.CalledProcessError:
        # AWS may reject deletion of an already-gone association after the
        # instance/ENI terminates. Reconcile actual state, never broaden IAM.
        refresh_state()
        retry, remaining = destroy_plan(
            variables, allowed, "destroy-detached-ip.tfplan"
        )
        if set(remaining) - {"aws_eip.demo", "aws_eip_association.demo"}:
            raise GuardError(
                "Cleanup failed with resources beyond a detached demo IP; inspect the private log and retry down"
            )
        ec2 = aws.client("ec2")
        tags = [
            {"Name": "tag:Project", "Values": ["wonderland"]},
            {"Name": "tag:Stack", "Values": [target_settings["name"]]},
        ]
        addresses = ec2.describe_addresses(Filters=tags)["Addresses"]
        if any(
            x.get(k)
            for x in addresses
            for k in ("AssociationId", "NetworkInterfaceId", "InstanceId")
        ):
            raise GuardError("Cleanup retry refused: demo IP is still associated")
        nodes = ec2.describe_instances(
            Filters=tags
            + [
                {
                    "Name": "instance-state-name",
                    "Values": [
                        "pending",
                        "running",
                        "stopping",
                        "stopped",
                        "shutting-down",
                    ],
                }
            ]
        )["Reservations"]
        if any(r["Instances"] for r in nodes):
            raise GuardError("Cleanup retry refused: a demo server is still present")
        print(
            "Retrying Terraform deletion of the detached demo IP within the approved scope. No IAM changes.",
            flush=True,
        )
        run_terraform("apply", "-input=false", "-no-color", str(retry))


def destroy(aws, target_settings, deployment_details, approved, allowed=None):
    if approved != "destroy-wonderland-demo":
        raise GuardError(
            "Destruction removes the demo database and cloud resources. Use ./cloud.sh destroy --approve destroy-wonderland-demo after preserving evidence"
        )
    # Always take a fresh off-server private backup before a complete release is removed.
    backup_if_present(aws, target_settings, deployment_details)
    override = TFROOT / "cleanup_override.tf.json"
    if override.exists():
        raise GuardError(
            "A cleanup override already exists; inspect the interrupted cleanup before continuing"
        )
    write_private_json(override, cleanup_override())
    try:
        # Reconcile externally terminated instances and stale EIP associations
        # before cleanup targets are selected. This changes only local TF state.
        refresh_state()
        variables = "-var-file=" + str(PRIVATE / "terraform.tfvars.json")
        # Disable the provider's deletion protections/force-delete flags using an
        # actual Terraform update, without recreating any application resource.
        state = json.loads(run_terraform("show", "-json", capture=True).stdout)
        resources = state.get("values", {}).get("root_module", {}).get("resources", [])
        targets = [
            r["address"]
            for r in resources
            if r["type"]
            in {
                "aws_cognito_user_pool",
                "aws_s3_bucket",
                "aws_ecr_repository",
                "aws_secretsmanager_secret",
            }
        ]
        if targets:
            preparation = PRIVATE / "cleanup-preparation.tfplan"
            run_terraform(
                "plan",
                "-input=false",
                "-no-color",
                variables,
                *["-target=" + x for x in targets],
                "-out=" + str(preparation),
            )
            preparation.chmod(0o600)
            change = json.loads(
                run_terraform("show", "-json", str(preparation), capture=True).stdout
            )
            if any(
                c["change"]["actions"] not in (["update"], ["no-op"], ["read"])
                for c in change.get("resource_changes", [])
            ):
                raise GuardError(
                    "Cleanup preparation would create/delete resources; refusing it"
                )
            run_terraform("apply", "-input=false", "-no-color", str(preparation))
        apply_destroy(aws, target_settings, variables, allowed)
    finally:
        override.unlink(missing_ok=True)
    if (PRIVATE / "stripe-endpoint.json").exists():
        endpoint = json.loads((PRIVATE / "stripe-endpoint.json").read_text())
        values = dotenv_values(ROOT / ".env", interpolate=False)
        key = values.get("APP_STRIPE_SECRET_KEY") or ""
        if not key.startswith("sk_test_"):
            raise GuardError("Only sandbox webhook cleanup is allowed")
        with httpx.Client(
            base_url="https://api.stripe.com/v1", auth=(key, ""), timeout=30
        ) as client:
            response = client.get("/webhook_endpoints/" + endpoint["id"])
            if response.status_code != 404:
                response.raise_for_status()
                obj = response.json()
                if obj.get("livemode") is not False or obj["url"] != endpoint["url"]:
                    raise GuardError("Sandbox webhook target differs; cleanup refused")
                client.delete("/webhook_endpoints/" + endpoint["id"]).raise_for_status()
        set_key(ROOT / ".env", "APP_STRIPE_WEBHOOK_SECRET", "")
        (ROOT / ".env").chmod(0o600)
    audit(aws, target_settings)
    if (PRIVATE / "deployment.json").exists():
        (PRIVATE / "deployment.json").rename(
            PRIVATE / ("destroyed-deployment-" + str(int(time.time())) + ".json")
        )
    archive = PRIVATE / "backups"
    archive.mkdir(exist_ok=True, mode=0o700)
    for filename in [
        "runtime.json",
        "accounts.json",
        "reporting.env",
        "stripe-endpoint.json",
    ]:
        if (PRIVATE / filename).exists():
            (PRIVATE / filename).rename(
                archive / (str(int(time.time())) + "-" + filename)
            )
    print(
        "Terraform destruction complete. Private backup and evidence remain on this Mac. IAM installer policies are retained and have no usage charge."
    )


def audit(aws, target_settings):
    name = target_settings["name"]
    tags = [
        {"Name": "tag:Project", "Values": ["wonderland"]},
        {"Name": "tag:Stack", "Values": [name]},
    ]
    ec2 = aws.client("ec2")
    remaining = []
    for api, key in [
        ("describe_vpcs", "Vpcs"),
        ("describe_subnets", "Subnets"),
        ("describe_network_interfaces", "NetworkInterfaces"),
        ("describe_addresses", "Addresses"),
        ("describe_volumes", "Volumes"),
        ("describe_internet_gateways", "InternetGateways"),
        ("describe_route_tables", "RouteTables"),
        ("describe_security_groups", "SecurityGroups"),
    ]:
        for row in getattr(ec2, api)(Filters=tags)[key]:
            remaining.append(
                {
                    "service": "ec2",
                    "type": key,
                    "id": next(
                        (
                            row[k]
                            for k in [
                                "VpcId",
                                "SubnetId",
                                "NetworkInterfaceId",
                                "AllocationId",
                                "VolumeId",
                                "InternetGatewayId",
                                "RouteTableId",
                                "GroupId",
                            ]
                            if k in row
                        ),
                        None,
                    ),
                }
            )
    reservations = ec2.describe_instances(
        Filters=tags
        + [
            {
                "Name": "instance-state-name",
                "Values": [
                    "pending",
                    "running",
                    "stopping",
                    "stopped",
                    "shutting-down",
                ],
            }
        ]
    )["Reservations"]
    remaining += [
        {"service": "ec2", "type": "instance", "id": x["InstanceId"]}
        for r in reservations
        for x in r["Instances"]
    ]
    for page in aws.client("ecr").get_paginator("describe_repositories").paginate():
        remaining += [
            {"service": "ecr", "id": x["repositoryName"]}
            for x in page["repositories"]
            if x["repositoryName"].startswith(name + "/")
        ]
    for page in aws.client("amplify").get_paginator("list_apps").paginate():
        remaining += [
            {"service": "amplify", "id": x["appId"]}
            for x in page["apps"]
            if x["name"].startswith(name + "-")
        ]
    for page in (
        aws.client("cognito-idp")
        .get_paginator("list_user_pools")
        .paginate(MaxResults=60)
    ):
        remaining += [
            {"service": "cognito", "id": x["Id"]}
            for x in page["UserPools"]
            if x["Name"].startswith(name + "-")
        ]
    for page in (
        aws.client("sqs")
        .get_paginator("list_queues")
        .paginate(QueueNamePrefix=name + "-")
    ):
        remaining += [{"service": "sqs", "id": x} for x in page.get("QueueUrls", [])]
    for page in (
        aws.client("logs")
        .get_paginator("describe_log_groups")
        .paginate(logGroupNamePrefix="/wonderland/" + name)
    ):
        remaining += [
            {"service": "logs", "id": x["logGroupName"]} for x in page["logGroups"]
        ]
    remaining += [
        {"service": "s3", "id": x["Name"]}
        for x in aws.client("s3").list_buckets()["Buckets"]
        if x["Name"].startswith(name + "-" + target_settings["account_id"] + "-")
    ]
    for page in aws.client("apigatewayv2").get_paginator("get_apis").paginate():
        remaining += [
            {"service": "apigateway", "id": x["ApiId"]}
            for x in page["Items"]
            if x["Name"] == name
        ]
    scheduled = []
    iam = aws.client("iam")
    for api, args in [
        ("get_role", {"RoleName": name + "-ec2"}),
        ("get_instance_profile", {"InstanceProfileName": name + "-ec2"}),
    ]:
        try:
            getattr(iam, api)(**args)
            remaining.append({"service": "iam", "type": api, "id": name + "-ec2"})
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchEntity":
                raise
    for page in (
        aws.client("secretsmanager")
        .get_paginator("list_secrets")
        .paginate(IncludePlannedDeletion=True)
    ):
        for x in page["SecretList"]:
            if x["Name"].startswith(name + "/"):
                (scheduled if x.get("DeletedDate") else remaining).append(
                    {"service": "secretsmanager", "id": x["Name"]}
                )
    report = {
        "checked_at": int(time.time()),
        "remaining_active_resources": remaining,
        "scheduled_recoverable_secrets": scheduled,
        "retained": "Private backups/evidence and non-billable IAM policy definitions/attachments",
    }
    write_private_json(PRIVATE / "cleanup-audit.json", report)
    if remaining:
        raise GuardError(
            "Cleanup inventory still finds demo resources; see secrets/simple-cloud/cleanup-audit.json"
        )
    print(
        "Cleanup inventory: no active demo resources found across compute/network/storage/registry/hosting/identity/API/queue/logs/secrets."
    )
    return report
