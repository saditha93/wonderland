"""Administrator Terraform IAM bootstrap; no account keys in this bundle."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import urllib.request
import zipfile
import boto3
import time
import shutil
import tempfile

VERSION = "1.16.6"


def checksum(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def provider_environment(folder, account_id):
    # CloudShell's persistent home is too small for the extracted AWS provider.
    # Keep state/reviews persistent, and only regenerable provider data in /tmp.
    data = Path(tempfile.gettempdir()) / f"wonderland-tf-{os.getuid()}-{account_id}"
    if data.is_symlink():
        raise ValueError("Provider cache must not be a symlink")
    data.mkdir(mode=0o700, exist_ok=True)
    if data.stat().st_uid != os.getuid():
        raise ValueError("Provider cache has a different owner")
    data.chmod(0o700)
    old_cache = folder / ".terraform"
    if old_cache.exists():
        destination = data / ("previous-home-cache-" + str(time.time_ns()))
        shutil.move(str(old_cache), str(destination))
    return dict(os.environ, TF_DATA_DIR=str(data))


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--review", required=True)
    p.add_argument("--apply")
    a = p.parse_args()
    bundle = json.loads(a.bundle.read_text())
    if (
        checksum(bundle) != a.review
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        != bundle["operator_sha256"]
    ):
        raise ValueError("Bundle/operator does not match the reviewed digest")
    s = boto3.Session(region_name="us-east-1")
    iam = s.client("iam")
    if s.client("sts").get_caller_identity()["Account"] != bundle["account_id"]:
        raise ValueError("Wrong administrator account")
    folder = Path.home() / ".wonderland/terraform-permissions" / bundle["account_id"]
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = provider_environment(folder, bundle["account_id"])
    plan = folder / "permissions.tfplan"
    review = folder / "plan-review.json"
    executable = folder / "terraform"
    if not executable.exists():
        arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
        if platform.system() != "Linux" or not arch:
            raise ValueError("Run this bootstrap in AWS CloudShell")
        name = f"terraform_{VERSION}_linux_{arch}.zip"
        base = f"https://releases.hashicorp.com/terraform/{VERSION}/"
        archive = urllib.request.urlopen(base + name, timeout=60).read()
        sums = (
            urllib.request.urlopen(base + f"terraform_{VERSION}_SHA256SUMS", timeout=60)
            .read()
            .decode()
        )
        expected = next(
            line.split()[0] for line in sums.splitlines() if line.split()[-1] == name
        )
        if hashlib.sha256(archive).hexdigest() != expected:
            raise ValueError("Official Terraform checksum differs")
        import io

        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            executable.write_bytes(z.read("terraform"))
        executable.chmod(0o700)

    def tf(*args, capture=False):
        r = subprocess.run(
            [str(executable), "-chdir=" + str(folder), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            env=environment,
        )
        return r.stdout

    for name, old in bundle["before"].items():
        arn = f"arn:aws:iam::{bundle['account_id']}:policy/{name}"
        policy = iam.get_policy(PolicyArn=arn)["Policy"]
        now = iam.get_policy_version(
            PolicyArn=arn, VersionId=policy["DefaultVersionId"]
        )["PolicyVersion"]["Document"]
        if now != old:
            raise ValueError(
                "Existing IAM definition changed; regenerate bundle: " + name
            )
    if a.apply:
        saved = json.loads(review.read_text())
        if (
            saved["bundle"] != a.review
            or a.apply != saved["plan"]
            or hashlib.sha256(plan.read_bytes()).hexdigest() != a.apply
            or time.time() - saved["created_at"] > 3600
        ):
            raise ValueError("Saved Terraform plan differs from approval")
        tf(
            "init",
            "-input=false",
            "-no-color",
            "-backend-config=path=" + str(folder / "terraform.tfstate"),
        )
        tf("apply", "-input=false", "-no-color", str(plan))
        for name, expected in bundle["documents"].items():
            arn = f"arn:aws:iam::{bundle['account_id']}:policy/{name}"
            version = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
            if (
                iam.get_policy_version(PolicyArn=arn, VersionId=version)[
                    "PolicyVersion"
                ]["Document"]
                != expected
            ):
                raise ValueError("Final policy verification differs: " + name)
        attached = {
            r["PolicyName"]
            for r in iam.list_attached_user_policies(UserName="wonderland")[
                "AttachedPolicies"
            ]
        }
        if (
            not (set(bundle["documents"]) - {"WonderlandRuntimeBoundary"}).issubset(
                attached
            )
            or "WonderlandRuntimeBoundary" in attached
        ):
            raise ValueError("Final user attachments differ")
        print(
            "Terraform permission bootstrap applied and verified. No compute or billing resources were created."
        )
        return
    (folder / "main.tf").write_text(bundle["main_tf"])
    variables = {
        k: bundle[k]
        for k in [
            "account_id",
            "existing_policies",
            "existing_attachments",
            "descriptions",
        ]
    }
    variables["documents"] = {
        k: json.dumps(v, separators=(",", ":")) for k, v in bundle["documents"].items()
    }
    (folder / "terraform.tfvars.json").write_text(json.dumps(variables))
    tf(
        "init",
        "-input=false",
        "-no-color",
        "-backend-config=path=" + str(folder / "terraform.tfstate"),
    )
    tf("plan", "-input=false", "-no-color", "-out=" + str(plan))
    document = json.loads(tf("show", "-json", str(plan), capture=True))
    for row in document.get("resource_changes", []):
        if row["type"] not in {
            "aws_iam_policy",
            "aws_iam_user_policy_attachment",
        } or row["change"]["actions"] not in (["no-op"], ["create"], ["update"]):
            raise ValueError(
                "Unexpected replacement/deletion/resource in permission plan"
            )
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    review.write_text(
        json.dumps({"bundle": a.review, "plan": digest, "created_at": int(time.time())})
    )
    print("Saved IAM plan digest:", digest)
    print("After explicit permission approval, rerun with --apply " + digest)


if __name__ == "__main__":
    main()
