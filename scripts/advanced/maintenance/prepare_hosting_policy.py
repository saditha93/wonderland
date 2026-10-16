"""Prepare and validate the two existing demo apps' publishing grant for review."""

import json, hashlib, copy, zipfile, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.aws.cli import (
    create_aws_session,
    load_target,
    load_deployment,
    PRIVATE,
    write_private_json,
)

s = create_aws_session(load_target())
d = load_deployment()
iam = s.client("iam")
account = load_target()["account_id"]
arn = f"arn:aws:iam::{account}:policy/WonderlandDemoServices"
v = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
before = iam.get_policy_version(PolicyArn=arn, VersionId=v)["PolicyVersion"]["Document"]


def digest(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


apps = sorted(p["app_id"] for p in d["portals"].values())
statement = {
    "Sid": "PublishExistingDemoDeploymentChildren",
    "Effect": "Allow",
    "Action": ["amplify:CreateDeployment", "amplify:StartDeployment"],
    "Resource": [
        f"arn:aws:amplify:us-east-1:{account}:apps/{a}/branches/demo/{kind}/*"
        for a in apps
        for kind in ["deployments", "jobs"]
    ],
    "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
}
after = copy.deepcopy(before)
after["Statement"].append(statement)
after["Statement"] = [
    r
    for r in before["Statement"]
    if r["Sid"] != "PublishExistingDemoDeploymentChildren"
] + [statement]
bundle = {
    "account": account,
    "policy_name": "WonderlandDemoServices",
    "before_sha256": digest(before),
    "app_ids": apps,
    "statement": statement,
    "after": after,
}
write_private_json(PRIVATE / "amplify-policy-update.json", bundle)
findings = s.client("accessanalyzer").validate_policy(
    policyDocument=json.dumps(after), policyType="IDENTITY_POLICY"
)["findings"]
assert not findings, findings
sim = iam.simulate_custom_policy(
    PolicyInputList=[json.dumps(after)],
    ActionNames=statement["Action"],
    ResourceArns=statement["Resource"],
    ContextEntries=[
        {
            "ContextKeyName": "aws:RequestedRegion",
            "ContextKeyType": "string",
            "ContextKeyValues": ["us-east-1"],
        }
    ],
)
assert all(x["EvalDecision"] == "allowed" for x in sim["EvaluationResults"])
negative = iam.simulate_custom_policy(
    PolicyInputList=[json.dumps({"Version": "2012-10-17", "Statement": [statement]})],
    ActionNames=statement["Action"],
    ResourceArns=[
        f"arn:aws:amplify:us-east-1:{account}:apps/unrelated/branches/demo/deployments/*",
        f"arn:aws:amplify:us-east-1:{account}:apps/{apps[0]}/branches/main/deployments/*",
    ],
    ContextEntries=[
        {
            "ContextKeyName": "aws:RequestedRegion",
            "ContextKeyType": "string",
            "ContextKeyValues": ["us-east-1"],
        }
    ],
)
assert all(x["EvalDecision"] == "implicitDeny" for x in negative["EvaluationResults"])
write_private_json(
    PRIVATE / "amplify-policy-validation.json",
    {
        "findings": findings,
        "allowed_cases": len(sim["EvaluationResults"]),
        "denied_cases": len(negative["EvaluationResults"]),
        "bundle_sha256": digest(bundle),
        "compact_policy_bytes": len(json.dumps(after, separators=(",", ":"))),
    },
)
print("Approval digest:", digest(bundle))
print(
    "Validation: zero findings;",
    len(sim["EvaluationResults"]),
    "allow and",
    len(negative["EvaluationResults"]),
    "deny cases passed. Bytes:",
    len(json.dumps(after, separators=(",", ":"))),
)
with zipfile.ZipFile(
    PRIVATE / "iam-amplify-deployment.zip", "w", zipfile.ZIP_DEFLATED
) as z:
    z.write(
        Path(__file__).resolve().parents[3]
        / "scripts/advanced/maintenance/update_hosting_policy.py",
        "update-demo-amplify-permission.py",
    )
    z.write(PRIVATE / "amplify-policy-update.json", "amplify-policy-update.json")
print(
    "Review the private bundle and upload secrets/simple-cloud/iam-amplify-deployment.zip to administrator CloudShell. Installation requires explicit approval; this command made no IAM changes."
)
