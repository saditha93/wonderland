"""Change only the reviewed EC2 size whitelist from an administrator CloudShell."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import boto3
from botocore.exceptions import ClientError


def checksum(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def install(bundle, approval):
    if (
        checksum(bundle) != approval
        or bundle["policy_name"] != "WonderlandDemoCompute"
        or bundle["user"] != "wonderland"
    ):
        raise ValueError("Unapproved compute-policy update")
    s = boto3.Session(region_name="us-east-1")
    account = bundle["account"]
    if s.client("sts").get_caller_identity()["Account"] != account:
        raise ValueError("Wrong administrator account")
    iam = s.client("iam")
    arn = f"arn:aws:iam::{account}:policy/WonderlandDemoCompute"
    if (
        iam.get_user(UserName="wonderland")["User"]["Arn"]
        != f"arn:aws:iam::{account}:user/wonderland"
    ):
        raise ValueError("Wrong user")
    policy = iam.get_policy(PolicyArn=arn)["Policy"]
    current = iam.get_policy_version(
        PolicyArn=arn, VersionId=policy["DefaultVersionId"]
    )["PolicyVersion"]["Document"]
    if current == bundle["after"]:
        print("Reviewed eligible size is already configured.")
        return
    if checksum(current) != bundle["before_sha256"]:
        raise ValueError("Existing policy differs from reviewed prior version")
    expected = copy.deepcopy(current)
    row = next(
        r for r in expected["Statement"] if r["Sid"] == "LaunchTaggedBoundedInstances"
    )
    row["Condition"]["StringEquals"]["ec2:InstanceType"] = ["m7i-flex.large"]
    if expected != bundle["after"]:
        raise ValueError("Update would alter more than the instance-type whitelist")
    findings = s.client("accessanalyzer").validate_policy(
        policyDocument=json.dumps(expected), policyType="IDENTITY_POLICY"
    )["findings"]
    if findings:
        raise ValueError("AWS policy validation requires review")
    iam.create_policy_version(
        PolicyArn=arn, PolicyDocument=json.dumps(expected), SetAsDefault=True
    )
    updated = iam.get_policy(PolicyArn=arn)["Policy"]
    verified = iam.get_policy_version(
        PolicyArn=arn, VersionId=updated["DefaultVersionId"]
    )["PolicyVersion"]["Document"]
    if verified != expected:
        raise ValueError("Final policy verification failed")
    print(
        "Verified compute whitelist now permits only m7i-flex.large. Ownership tags, region, encryption and runtime boundary were not changed."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--approve", required=True)
    a = p.parse_args()
    try:
        install(json.loads(a.bundle.read_text()), a.approve)
    except (ValueError, ClientError) as exc:
        if isinstance(exc, ValueError):
            raise SystemExit(str(exc)) from None
        raise SystemExit(
            "Compute policy update failed: " + exc.response["Error"]["Code"]
        ) from None
