"""Build and install public application artifacts on the AWS server."""

import hashlib
import json
import shlex
import time
import zipfile
from botocore.exceptions import ClientError
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    write_private_json,
)


from scripts.aws.remote import run_on_server


def publish_images(aws, target_settings, deployment_details):
    """Build in AWS to avoid large image uploads over the local connection."""
    client = aws.client("ecr")
    missing = []
    for name in deployment_details["repositories"]:
        try:
            client.describe_images(
                repositoryName=target_settings["name"] + "/" + name,
                imageIds=[{"imageTag": target_settings["release"]}],
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ImageNotFoundException":
                raise
            missing.append(name)
    if not missing:
        return
    path = PRIVATE / "build-source.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in [
            "requirements.lock",
            ".dockerignore",
            "infrastructure/local/Dockerfile.migrate",
            "scripts/db_migrate.py",
            "scripts/cloud_migrate.py",
            "scripts/aws/image_builder.py",
        ]:
            z.write(ROOT / name, name)
        for folder in ["services", "wonderland_common", "frontend"]:
            for f in sorted((ROOT / folder).rglob("*")):
                relative = f.relative_to(ROOT)
                if not f.is_file() or any(
                    x in {"node_modules", "dist", "dist-admin", "__pycache__", ".git"}
                    for x in relative.parts
                ):
                    continue
                if (
                    f.name.startswith(".env")
                    or f.suffix in {".pyc", ".pem"}
                    and f.name != "rds-global-bundle.pem"
                ):
                    continue
                z.write(f, str(relative))
        z.writestr(
            "build-config.json",
            json.dumps(
                {
                    "target": target_settings,
                    "deployment": deployment_details,
                    "missing": missing,
                }
            ),
        )
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = "releases/" + target_settings["release"] + "/build-" + digest + ".zip"
    aws.client("s3").upload_file(
        str(path),
        deployment_details["artifact_bucket"],
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    sm = aws.client("secretsmanager")
    value = json.loads((PRIVATE / "runtime.json").read_text())
    auth = client.get_authorization_token()["authorizationData"][0]
    if (
        auth["proxyEndpoint"]
        != f"https://{target_settings['account_id']}.dkr.ecr.{target_settings['region']}.amazonaws.com"
    ):
        raise GuardError("Unexpected build registry")
    value["build_registry_auth"] = {
        k: auth[k] for k in ["authorizationToken", "proxyEndpoint"]
    }
    sm.put_secret_value(
        SecretId=deployment_details["runtime_secret_arn"],
        SecretString=json.dumps(value),
    )
    downloader = f"""import boto3,hashlib,io,zipfile,pathlib
body=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details["artifact_bucket"]!r},Key={key!r})['Body'].read()
assert hashlib.sha256(body).hexdigest()=={digest!r}
root=pathlib.Path('/opt/wonderland/build-source')
assert not root.is_symlink()
import shutil
if root.exists(): shutil.rmtree(root)
with zipfile.ZipFile(io.BytesIO(body)) as z:
 for name in z.namelist():
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
 z.extractall(root)
"""
    try:
        run_on_server(
            aws,
            deployment_details,
            [
                "set -eu",
                "umask 077",
                "for n in $(seq 1 180); do test -f /opt/wonderland/bootstrap-ready && break; sleep 5; done",
                "test -f /opt/wonderland/bootstrap-ready",
                "export DEBIAN_FRONTEND=noninteractive",
                "apt-get update -qq && apt-get install -y -qq docker.io",
                "systemctl start docker",
                "python3 -c " + shlex.quote(downloader),
                "python3 /opt/wonderland/build-source/scripts/aws/image_builder.py /opt/wonderland/build-source/build-config.json",
            ],
            timeout=2400,
        )
        for name in missing:
            client.describe_images(
                repositoryName=target_settings["name"] + "/" + name,
                imageIds=[{"imageTag": target_settings["release"]}],
            )
        print("All six immutable images verified in ECR after private on-node build.")
    finally:
        value.pop("build_registry_auth", None)
        sm.put_secret_value(
            SecretId=deployment_details["runtime_secret_arn"],
            SecretString=json.dumps(value),
        )


def install_workloads(aws, target_settings, deployment_details):
    path = PRIVATE / "node.zip"
    write_private_json(
        PRIVATE / "node-config.json",
        {"target": target_settings, "deployment": deployment_details},
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        files = [
            "scripts/__init__.py",
            "scripts/aws/__init__.py",
            "scripts/aws/workload_templates.py",
            "scripts/aws/workloads.py",
            "infrastructure/aws/node.py",
            "analytics/dashboard.json",
        ]
        files += [str(p.relative_to(ROOT)) for p in (ROOT / "analytics").rglob("*.sql")]
        files += [
            str(p.relative_to(ROOT))
            for folder in [
                "infrastructure/kubernetes/base",
                "infrastructure/kubernetes/local",
                "infrastructure/kubernetes/aws",
            ]
            for p in (ROOT / folder).glob("*.yaml")
        ]
        files += ["frontend/nginx.conf", "wonderland_common/rds-global-bundle.pem"]
        for name in files:
            archive.write(ROOT / name, name)
        archive.write(PRIVATE / "node-config.json", "node-config.json")
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = "releases/" + target_settings["release"] + "/" + digest + ".zip"
    aws.client("s3").upload_file(
        str(path),
        deployment_details["artifact_bucket"],
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    downloader = f"""import boto3,hashlib,io,zipfile,pathlib
body=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details["artifact_bucket"]!r},Key={key!r})['Body'].read()
assert hashlib.sha256(body).hexdigest()=={digest!r}
root=pathlib.Path('/opt/wonderland/source')
with zipfile.ZipFile(io.BytesIO(body)) as z:
 for name in z.namelist():
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
 z.extractall(root)
"""
    commands = [
        "set -eu",
        "umask 077",
        "for n in $(seq 1 180); do test -f /opt/wonderland/bootstrap-ready && break; sleep 5; done",
        "test -f /opt/wonderland/bootstrap-ready",
        "python3 -c " + shlex.quote(downloader),
        "python3 -m venv --clear /opt/wonderland/runtime",
        "/opt/wonderland/runtime/bin/pip install --disable-pip-version-check boto3==1.43.113 pyyaml==6.0.3 cryptography==50.0.2 sqlalchemy==2.1.4",
        "/opt/wonderland/runtime/bin/python /opt/wonderland/source/infrastructure/aws/node.py install --config /opt/wonderland/source/node-config.json",
    ]
    run_on_server(aws, deployment_details, commands)


def publish_websites(aws, target_settings, deployment_details):
    amplify = aws.client("amplify")
    jobs = {}
    for name, portal in deployment_details["portals"].items():
        response = amplify.create_deployment(appId=portal["app_id"], branchName="demo")
        jobs[name] = {k: response[k] for k in ["jobId", "zipUploadUrl"]}
        write_private_json(PRIVATE / "server-hosting-jobs.json", jobs)
    sm = aws.client("secretsmanager")
    value = json.loads((PRIVATE / "runtime.json").read_text())
    value["build_hosting_jobs"] = jobs
    sm.put_secret_value(
        SecretId=deployment_details["runtime_secret_arn"],
        SecretString=json.dumps(value),
    )
    body = (ROOT / "scripts/aws/site_builder.py").read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    key = "releases/" + target_settings["release"] + "/hosting-" + digest + ".py"
    aws.client("s3").put_object(
        Bucket=deployment_details["artifact_bucket"],
        Key=key,
        Body=body,
        ServerSideEncryption="AES256",
    )
    downloader = f"import boto3,hashlib,pathlib;b=boto3.client('s3',region_name='us-east-1').get_object(Bucket={deployment_details['artifact_bucket']!r},Key={key!r})['Body'].read();assert hashlib.sha256(b).hexdigest()=={digest!r};pathlib.Path('/opt/wonderland/server-hosting.py').write_bytes(b)"
    try:
        run_on_server(
            aws,
            deployment_details,
            [
                "set -eu",
                "umask 077",
                "python3 -c " + shlex.quote(downloader),
                "python3 /opt/wonderland/server-hosting.py",
            ],
            timeout=600,
        )
    finally:
        value.pop("build_hosting_jobs", None)
        sm.put_secret_value(
            SecretId=deployment_details["runtime_secret_arn"],
            SecretString=json.dumps(value),
        )
    for name, portal in deployment_details["portals"].items():
        job = jobs[name]
        amplify.start_deployment(
            appId=portal["app_id"], branchName="demo", jobId=job["jobId"]
        )
        for _ in range(60):
            status = amplify.get_job(
                appId=portal["app_id"], branchName="demo", jobId=job["jobId"]
            )["job"]["summary"]["status"]
            if status == "SUCCEED":
                break
            if status in {"FAILED", "CANCELLED"}:
                raise GuardError("Amplify " + name + " publishing failed")
            time.sleep(5)
        else:
            raise GuardError("Amplify publishing timed out")
        print("Server-built Amplify portal ready:", portal["origin"])
