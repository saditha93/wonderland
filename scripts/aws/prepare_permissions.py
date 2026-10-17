"""Read-only preparation of the administrator's Terraform permission bootstrap."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from botocore.exceptions import ClientError
from scripts.aws.cli import (
    ROOT,
    PRIVATE,
    load_target,
    create_aws_session,
    write_private_json,
)
from scripts.aws.policies import policies, dependencies


def main():
    t = load_target()
    s = create_aws_session(t)
    iam = s.client("iam")
    documents = policies(t["account_id"], ssh_key_pair_id=t.get("ssh_key_pair_id"))
    documents["WonderlandDemoDependencies"] = dependencies(t["account_id"])
    existing = []
    descriptions = {}
    before = {}
    findings = {}
    attached = {
        p["PolicyName"]
        for p in iam.list_attached_user_policies(UserName="wonderland")[
            "AttachedPolicies"
        ]
    }
    if "WonderlandRuntimeBoundary" in attached:
        raise ValueError("Runtime boundary must not be attached to the deployment user")
    for name, doc in documents.items():
        findings[name] = s.client("accessanalyzer").validate_policy(
            policyDocument=json.dumps(doc), policyType="IDENTITY_POLICY"
        )["findings"]
        if findings[name]:
            raise ValueError("Policy validation requires review: " + name)
        try:
            old = iam.get_policy(
                PolicyArn=f"arn:aws:iam::{t['account_id']}:policy/{name}"
            )["Policy"]
            existing.append(name)
            descriptions[name] = old.get("Description", "")
            before[name] = iam.get_policy_version(
                PolicyArn=old["Arn"], VersionId=old["DefaultVersionId"]
            )["PolicyVersion"]["Document"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchEntity":
                raise
            descriptions[name] = "Reviewed Wonderland EC2 demo deployment permissions"
    main_tf = (ROOT / "infrastructure/terraform/permissions/main.tf").read_text()
    payload = {
        "account_id": t["account_id"],
        "documents": documents,
        "before": before,
        "existing_policies": sorted(existing),
        "existing_attachments": sorted(
            (set(documents) - {"WonderlandRuntimeBoundary"}) & attached
        ),
        "descriptions": descriptions,
        "main_tf": main_tf,
        "operator_sha256": hashlib.sha256(
            (ROOT / "infrastructure/terraform/permissions/bootstrap.py").read_bytes()
        ).hexdigest(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    folder = PRIVATE / "terraform-permissions"
    folder.mkdir(exist_ok=True, mode=0o700)
    write_private_json(folder / "payload.json", payload)
    write_private_json(
        folder / "validation.json",
        {
            "findings": findings,
            "bundle_sha256": digest,
            "changed_definitions": [
                n for n in documents if before.get(n) != documents[n]
            ],
        },
    )
    archive = PRIVATE / "terraform-permissions.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(folder / "payload.json", "payload.json")
        z.write(
            ROOT / "infrastructure/terraform/permissions/bootstrap.py", "bootstrap.py"
        )
    archive.chmod(0o600)
    print("Prepared administrator Terraform bundle:", archive)
    print("AWS validation: zero findings across all five documents.")
    print(
        "Definitions changing:", [n for n in documents if before.get(n) != documents[n]]
    )
    print("Review bundle digest:", digest)
    print(
        "CloudShell plan: python3 bootstrap.py --bundle payload.json --review " + digest
    )


if __name__ == "__main__":
    main()
