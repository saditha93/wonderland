"""AWS lifecycle commands for Wonderland; credentials and state stay private."""

import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile
import fcntl
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import boto3
from botocore.exceptions import ClientError
from scripts.aws.credentials import GuardError, load_credentials
from scripts.aws.policies import policies

PRIVATE = ROOT / "secrets/simple-cloud"
TFROOT = ROOT / "infrastructure/terraform/aws"
TF = shutil.which("terraform") or str(ROOT / "tmp/tools/terraform")


def aws_environment(settings):
    return load_credentials(settings, ROOT)


@contextmanager
def operation_lock():
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (PRIVATE / "operation.lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GuardError(
                "Another cloud operation is running. Let it finish before up/down/release."
            ) from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write_private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def load_target():
    value = json.loads((PRIVATE / "target.json").read_text())
    if (
        value["region"] != "us-east-1"
        or value["name"] != "wonderland-demo"
        or not re.fullmatch(r"\d{12}", value["account_id"])
    ):
        raise GuardError("Unexpected demo target")
    if (
        value["instance_type"] != "m7i-flex.large"
        or value.get("architecture") != "amd64"
    ):
        raise GuardError("Unreviewed instance size")
    if not re.fullmatch(r"[a-z0-9-]{1,40}", value["release"]):
        raise GuardError("Invalid immutable release identifier")
    return value


def create_aws_session(target_settings):
    aws = boto3.Session(
        region_name=target_settings["region"], **aws_environment(target_settings)
    )
    identity = aws.client("sts").get_caller_identity()
    if (
        identity["Account"] != target_settings["account_id"]
        or identity["Arn"]
        != f"arn:aws:iam::{target_settings['account_id']}:user/wonderland"
    ):
        raise GuardError("Deploy using the reviewed non-root wonderland IAM user")
    return aws


def require_free_plan(aws):
    account = aws.client("freetier").get_account_plan_state()
    if (
        account.get("accountPlanType") != "FREE"
        or account.get("accountPlanStatus") != "ACTIVE"
    ):
        raise GuardError(
            "Expected an active AWS Free plan; no automatic upgrade is permitted"
        )
    return account


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def run_terraform(*args, capture=False):
    env = {
        **os.environ,
        "TF_IN_AUTOMATION": "true",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    return run(
        [TF, "-chdir=" + str(TFROOT), *args],
        env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def source_fingerprint():
    digest = hashlib.sha256()
    for name in (
        "requirements.lock",
        "requirements.in",
        "pyproject.toml",
        ".dockerignore",
        "cloud.sh",
        "demo.sh",
    ):
        digest.update(name.encode())
        digest.update((ROOT / name).read_bytes())
    for directory in (
        "infrastructure",
        "scripts",
        "frontend",
        "services",
        "wonderland_common",
        "analytics",
    ):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.name == "cleanup_override.tf.json":
                continue
            if not path.is_file() or any(
                part
                in {".terraform", "__pycache__", "node_modules", "dist", "dist-admin"}
                for part in path.parts
            ):
                continue
            if path.suffix in {".pyc", ".tfstate"}:
                continue
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def plan(aws, target_settings):
    if (TFROOT / "cleanup_override.tf.json").exists():
        raise GuardError(
            "Remove/review the interrupted cleanup override before a deployment plan"
        )
    require_free_plan(aws)
    ec2 = aws.client("ec2")
    selected = ec2.describe_instance_types(
        InstanceTypes=[target_settings["instance_type"]]
    )["InstanceTypes"][0]
    if (
        not selected.get("FreeTierEligible")
        or selected["MemoryInfo"]["SizeInMiB"] < 8192
    ):
        raise GuardError(
            "Selected size must be Free-plan eligible and have at least 8 GiB for this complete demo"
        )
    image = ec2.describe_images(ImageIds=[target_settings["ami_id"]])["Images"]
    if (
        len(image) != 1
        or image[0]["State"] != "available"
        or image[0]["Architecture"] != "x86_64"
        or image[0]["OwnerId"] != "099720109477"
    ):
        raise GuardError("Expected an available official Ubuntu x86-64 image")
    offers = ec2.describe_instance_type_offerings(
        LocationType="availability-zone",
        Filters=[
            {"Name": "instance-type", "Values": [target_settings["instance_type"]]}
        ],
    )["InstanceTypeOfferings"]
    zones = {
        z["ZoneName"]
        for z in ec2.describe_availability_zones(
            Filters=[{"Name": "state", "Values": ["available"]}]
        )["AvailabilityZones"]
    }
    possible = sorted(o["Location"] for o in offers if o["Location"] in zones)
    if not possible:
        raise GuardError("No available zone supports the selected instance")
    target_settings.setdefault("availability_zone", possible[0])
    if target_settings["availability_zone"] not in possible:
        raise GuardError("Pinned zone is unavailable")
    write_private_json(PRIVATE / "target.json", target_settings)
    tokenfile = PRIVATE / "origin-token.json"
    if not tokenfile.exists():
        import secrets

        write_private_json(tokenfile, {"token": secrets.token_urlsafe(48)})
    bootstrap = (ROOT / "infrastructure/aws/bootstrap.sh").read_text()
    variables = {
        k: target_settings[k]
        for k in ("account_id", "ami_id", "availability_zone", "instance_type")
    }
    key_name = target_settings.get("ssh_key_name", "sliit_test")
    ssh_cidr = target_settings.get("ssh_allowed_cidr", "")
    try:
        network = ipaddress.IPv4Network(ssh_cidr, strict=True)
        if network.prefixlen != 32 or not network.network_address.is_global:
            raise ValueError("Expected one public IPv4 address")
    except ValueError as exc:
        raise GuardError(
            "Set ssh_allowed_cidr to your public IPv4 address followed by /32"
        ) from exc
    key = ec2.describe_key_pairs(KeyNames=[key_name], IncludePublicKey=True)[
        "KeyPairs"
    ][0]
    pem = Path(
        target_settings.get("ssh_private_key_path", "~/Projects/pem/sliit_test.pem")
    ).expanduser()
    if not pem.is_file() or pem.stat().st_mode & 0o077:
        raise GuardError("SSH private key must exist locally with mode 400 or 600")
    public = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(pem)], check=True, capture_output=True, text=True
    ).stdout.split()
    if public[:2] != key.get("PublicKey", "").split()[:2]:
        raise GuardError("Local PEM does not match the existing AWS key pair")
    target_settings["ssh_key_pair_id"] = key["KeyPairId"]
    write_private_json(PRIVATE / "target.json", target_settings)
    variables.update(
        server_name=target_settings.get("server_name", "Wonderland Demo Server"),
        ssh_key_name=key_name,
        ssh_allowed_cidr=ssh_cidr,
        bootstrap_script=bootstrap,
        runtime_policy=json.dumps(
            policies(target_settings["account_id"])["WonderlandRuntimeBoundary"]
        ),
        origin_token=json.loads(tokenfile.read_text())["token"],
    )
    write_private_json(PRIVATE / "terraform.tfvars.json", variables)
    run_terraform("init", "-input=false", "-reconfigure")
    run_terraform(
        "plan",
        "-input=false",
        "-no-color",
        "-var-file=" + str(PRIVATE / "terraform.tfvars.json"),
        "-out=" + str(PRIVATE / "deployment.tfplan"),
    )
    p = PRIVATE / "deployment.tfplan"
    p.chmod(0o600)
    document = json.loads(run_terraform("show", "-json", str(p), capture=True).stdout)
    changes = [
        {"address": c["address"], "actions": c["change"]["actions"]}
        for c in document.get("resource_changes", [])
        if c["change"]["actions"] != ["no-op"]
    ]
    # A later deployment may not silently replace the server/database or delete resources.
    if any("delete" in c["actions"] for c in changes):
        raise GuardError(
            "Plan includes deletion/replacement; backup and separate review required"
        )
    review = {
        "plan_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "source_sha256": source_fingerprint(),
        "target": target_settings,
        "changes": changes,
        "created_at": int(time.time()),
    }
    write_private_json(PRIVATE / "review.json", review)
    print("\nSaved reviewed plan:", review["plan_sha256"])
    print(
        "Observed compute quote: $0.09576/hour for eligible m7i-flex.large (8 GiB); storage, IPv4 and AWS services are additional. Credits/Free plan are not a zero-cost guarantee."
    )
    print(
        "Compute automatically stops six hours after boot. Storage and IPv4 remain allocated."
    )
    print(
        "Apply exactly this plan: ./cloud.sh deploy --approve " + review["plan_sha256"]
    )


def load_deployment():
    if not (PRIVATE / "deployment.json").exists():
        raise GuardError(
            "No active deployment is recorded. Use ./cloud.sh up to review a new deployment, or cleanup-check to check AWS."
        )
    return json.loads((PRIVATE / "deployment.json").read_text())


def check_cleanup_permissions(aws, target_settings):
    result = aws.client("iam").simulate_principal_policy(
        PolicySourceArn=f"arn:aws:iam::{target_settings['account_id']}:user/wonderland",
        ActionNames=["s3:DeleteObjectVersion"],
        ResourceArns=[
            f"arn:aws:s3:::wonderland-demo-{target_settings['account_id']}-artifacts/releases/preflight"
        ],
    )
    if any(x["EvalDecision"] != "allowed" for x in result["EvaluationResults"]):
        raise GuardError(
            "One-time Terraform permissions setup is required: S3 version cleanup is not allowed. No infrastructure was created. See docs/deployment.md."
        )

    if target_settings.get("ssh_key_name"):
        key_arn = f"arn:aws:ec2:{target_settings['region']}:{target_settings['account_id']}:key-pair/{target_settings['ssh_key_name']}"
        result = aws.client("iam").simulate_principal_policy(
            PolicySourceArn=f"arn:aws:iam::{target_settings['account_id']}:user/wonderland",
            ActionNames=["ec2:RunInstances"],
            ResourceArns=[key_arn],
            ContextEntries=[
                {
                    "ContextKeyName": "aws:RequestedRegion",
                    "ContextKeyValues": [target_settings["region"]],
                    "ContextKeyType": "string",
                }
            ],
        )
        if any(x["EvalDecision"] != "allowed" for x in result["EvaluationResults"]):
            raise GuardError(
                "Retained IAM policies are missing the SSH key-name grant. Apply the one-time administrator Terraform correction for key-pair/sliit_test. Normal down retains these policies. See docs/deployment.md. No infrastructure created."
            )


def up(aws, target_settings, approved, infra_only=False):
    check_cleanup_permissions(aws, target_settings)
    if not approved:
        plan(aws, target_settings)
        approved = json.loads((PRIVATE / "review.json").read_text())["plan_sha256"]
    # EC2 authorizes RunInstances against the key-pair NAME, not its key-* ID.
    check_cleanup_permissions(aws, target_settings)
    deploy(aws, target_settings, approved)
    if not infra_only:
        from scripts.aws.release import release_application

        release_application(aws, target_settings, load_deployment())


def deploy(aws, target_settings, approved):
    review = json.loads((PRIVATE / "review.json").read_text())
    p = PRIVATE / "deployment.tfplan"
    if (
        approved != review["plan_sha256"]
        or hashlib.sha256(p.read_bytes()).hexdigest() != approved
    ):
        raise GuardError("Supply the exact saved plan digest shown by ./cloud.sh plan")
    if (
        review["source_sha256"] != source_fingerprint()
        or review["target"] != target_settings
        or time.time() - review["created_at"] > 3600
    ):
        raise GuardError(
            "Source/target changed or plan is older than one hour; run plan again"
        )
    require_free_plan(aws)
    run_terraform("apply", "-input=false", "-no-color", str(p))
    for f in PRIVATE.glob("*.tfstate*"):
        f.chmod(0o600)
    value = json.loads(run_terraform("output", "-json", capture=True).stdout)[
        "deployment"
    ]["value"]
    write_private_json(PRIVATE / "deployment.json", value)
    print(
        "AWS resources created. Run ./cloud.sh release to install and verify the application."
    )


def status(aws, target_settings):
    deployment_details = load_deployment()
    rows = aws.client("ec2").describe_instances(
        InstanceIds=[deployment_details["instance_id"]]
    )["Reservations"]
    instance = rows[0]["Instances"][0]
    print("Server:", instance["State"]["Name"], "IP:", deployment_details["server_ip"])
    for name, portal in deployment_details["portals"].items():
        print(name.capitalize() + ":", portal["origin"])
    print("API:", deployment_details["api_url"])
    print("Name:", target_settings.get("server_name", "Wonderland Demo Server"))
    print(
        "SSH: ssh -i",
        target_settings.get("ssh_private_key_path", "~/Projects/pem/sliit_test.pem"),
        "ubuntu@" + deployment_details["server_ip"],
    )
    print("Metabase: ./cloud.sh monitoring (private tunnel)")


def set_server_power(aws, target_settings, action):
    require_free_plan(aws)
    deployment_details = load_deployment()
    ec2 = aws.client("ec2")
    instance = ec2.describe_instances(InstanceIds=[deployment_details["instance_id"]])[
        "Reservations"
    ][0]["Instances"][0]
    tags = {x["Key"]: x["Value"] for x in instance.get("Tags", [])}
    if tags.get("Project") != "wonderland" or tags.get("Stack") != "wonderland-demo":
        raise GuardError("Instance ownership tags differ")
    getattr(ec2, action + "_instances")(InstanceIds=[deployment_details["instance_id"]])
    print(action.capitalize() + " requested; database and address are preserved.")


def dispatch(args, aws, target_settings):
    if args.action == "up":
        up(aws, target_settings, args.approve, args.infra_only)
    elif args.action in {"plan-down", "down"}:
        from scripts.aws.cleanup import plan_down, down

        if args.action == "plan-down":
            plan_down(aws, target_settings)
        elif args.approve:
            down(aws, target_settings, args.approve)
        else:
            digest = plan_down(aws, target_settings)
            down(aws, target_settings, digest)
    elif args.action == "plan":
        plan(aws, target_settings)
    elif args.action == "deploy":
        check_cleanup_permissions(aws, target_settings)
        deploy(aws, target_settings, args.approve)
    elif args.action == "status":
        if (PRIVATE / "deployment.json").exists():
            status(aws, target_settings)
        else:
            print(
                "No active deployment is recorded. Use cleanup-check to verify AWS, or up to review a deployment."
            )
    elif args.action in {"start", "stop"}:
        set_server_power(aws, target_settings, args.action)
    elif args.action in {"backup", "destroy", "cleanup-check"}:
        from scripts.aws.cleanup import backup, destroy, audit

        if args.action == "cleanup-check":
            audit(aws, target_settings)
        elif args.action == "backup":
            backup(aws, target_settings, load_deployment())
        else:
            value = (
                json.loads(run_terraform("output", "-json", capture=True).stdout)
                .get("deployment", {})
                .get("value")
            )
            destroy(aws, target_settings, value, args.approve)
    else:
        from scripts.aws.release import release_application
        from scripts.aws.verification import verify_deployment, open_monitoring_tunnel

        {
            "release": release_application,
            "verify": verify_deployment,
            "monitoring": open_monitoring_tunnel,
        }[args.action](aws, target_settings, load_deployment())


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=[
            "up",
            "plan-down",
            "down",
            "plan",
            "deploy",
            "release",
            "verify",
            "status",
            "start",
            "stop",
            "monitoring",
            "backup",
            "destroy",
            "cleanup-check",
        ],
    )
    p.add_argument("--approve")
    p.add_argument(
        "--infra-only",
        action="store_true",
        help="For up: provision infrastructure without application release",
    )
    args = p.parse_args()
    target_settings = load_target()
    aws = create_aws_session(target_settings)
    if args.action in {"status", "cleanup-check", "monitoring"}:
        dispatch(args, aws, target_settings)
    else:
        with operation_lock():
            dispatch(args, aws, target_settings)


if __name__ == "__main__":
    try:
        main()
    except ClientError as exc:
        raise SystemExit(
            "AWS refused the operation: "
            + exc.response["Error"]["Code"]
            + ". No plan upgrade or broad permission fallback was attempted."
        ) from None
    except (GuardError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Cloud command failed. AWS changes may be partial; inspect the private operation log and use cleanup-check before assuming resources are gone."
        ) from None
