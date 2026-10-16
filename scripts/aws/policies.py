"""Generate reviewable IAM policies for the domain-free EC2 demo; no AWS calls."""

import argparse
import json
from pathlib import Path
import re


def policies(account, region="us-east-1", name="wonderland-demo"):
    if (
        not re.fullmatch(r"\d{12}", account)
        or region != "us-east-1"
        or name != "wonderland-demo"
    ):
        raise ValueError(
            "This demo policy supports an explicit account and the reviewed us-east-1/wonderland-demo scope"
        )
    statements = []
    regional = {"StringEquals": {"aws:RequestedRegion": region}}
    request_tags = {
        "StringEquals": {
            "aws:RequestedRegion": region,
            "aws:RequestTag/Project": "wonderland",
            "aws:RequestTag/Stack": name,
        }
    }
    resource_tags = {
        "StringEquals": {
            "aws:RequestedRegion": region,
            "aws:ResourceTag/Project": "wonderland",
            "aws:ResourceTag/Stack": name,
        }
    }
    ec2_tags = {
        "StringEquals": {
            "aws:RequestedRegion": region,
            "ec2:ResourceTag/Project": "wonderland",
            "ec2:ResourceTag/Stack": name,
        }
    }

    def add(sid, actions, resources, condition=None):
        row = {"Sid": sid, "Effect": "Allow", "Action": actions, "Resource": resources}
        if condition:
            row["Condition"] = condition
        statements.append(row)

    def arn(service, suffix):
        return f"arn:aws:{service}:{region}:{account}:{suffix}"

    ec2 = lambda kind: arn("ec2", kind + "/*")
    creates = [
        "CreateVpc",
        "CreateSubnet",
        "CreateRouteTable",
        "CreateInternetGateway",
        "CreateSecurityGroup",
        "CreateNetworkInterface",
        "AllocateAddress",
    ]
    add("CreateTaggedDemoNetwork", ["ec2:" + a for a in creates], "*", request_tags)
    add(
        "ManageTaggedDemoNetwork",
        [
            "ec2:" + a
            for a in [
                "DeleteVpc",
                "ModifyVpcAttribute",
                "DeleteSubnet",
                "ModifySubnetAttribute",
                "DeleteRouteTable",
                "CreateRoute",
                "ReplaceRoute",
                "DeleteRoute",
                "AssociateRouteTable",
                "DisassociateRouteTable",
                "AttachInternetGateway",
                "DetachInternetGateway",
                "DeleteInternetGateway",
                "DeleteSecurityGroup",
                "AuthorizeSecurityGroupIngress",
                "AuthorizeSecurityGroupEgress",
                "RevokeSecurityGroupIngress",
                "RevokeSecurityGroupEgress",
                "DeleteNetworkInterface",
                "AssociateAddress",
                "DisassociateAddress",
                "ReleaseAddress",
            ]
        ],
        [
            ec2(k)
            for k in [
                "vpc",
                "subnet",
                "route-table",
                "internet-gateway",
                "security-group",
                "network-interface",
                "elastic-ip",
                "instance",
            ]
        ],
        ec2_tags,
    )
    launch_tags = json.loads(json.dumps(request_tags))
    launch_tags["StringEquals"]["ec2:InstanceType"] = ["m7i-flex.large"]
    add(
        "LaunchTaggedBoundedInstances", "ec2:RunInstances", ec2("instance"), launch_tags
    )
    add(
        "LaunchEncryptedVolumes",
        "ec2:RunInstances",
        ec2("volume"),
        {
            "StringEquals": request_tags["StringEquals"],
            "Bool": {"ec2:Encrypted": "true"},
        },
    )
    add(
        "UseTaggedNetworkForLaunch",
        "ec2:RunInstances",
        [ec2(k) for k in ["subnet", "security-group", "network-interface"]],
        ec2_tags,
    )
    add(
        "UsePublicMachineImages",
        "ec2:RunInstances",
        f"arn:aws:ec2:{region}::image/*",
        regional,
    )
    add(
        "ManageTaggedInstances",
        [
            "ec2:StartInstances",
            "ec2:StopInstances",
            "ec2:TerminateInstances",
            "ec2:ModifyInstanceMetadataOptions",
        ],
        ec2("instance"),
        ec2_tags,
    )
    tagging = json.loads(json.dumps(request_tags))
    tagging["StringEquals"]["ec2:CreateAction"] = creates + ["RunInstances"]
    add(
        "TagAtCreation",
        "ec2:CreateTags",
        [
            ec2(k)
            for k in [
                "vpc",
                "subnet",
                "route-table",
                "internet-gateway",
                "security-group",
                "network-interface",
                "elastic-ip",
                "instance",
                "volume",
            ]
        ],
        tagging,
    )
    updates = json.loads(json.dumps(ec2_tags))
    updates["ForAllValues:StringNotEquals"] = {"aws:TagKeys": ["Project", "Stack"]}
    add(
        "MaintainNonOwnershipTags",
        ["ec2:CreateTags", "ec2:DeleteTags"],
        f"arn:aws:ec2:{region}:{account}:*/*",
        updates,
    )
    add(
        "ProjectContainerImages",
        [
            "ecr:CreateRepository",
            "ecr:DeleteRepository",
            "ecr:PutLifecyclePolicy",
            "ecr:DeleteLifecyclePolicy",
            "ecr:PutImage",
            "ecr:BatchDeleteImage",
            "ecr:InitiateLayerUpload",
            "ecr:UploadLayerPart",
            "ecr:CompleteLayerUpload",
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer",
            "ecr:TagResource",
            "ecr:UntagResource",
        ],
        arn("ecr", f"repository/{name}/*"),
        regional,
    )
    add("ContainerRegistryLogin", "ecr:GetAuthorizationToken", "*", regional)
    bucket = f"arn:aws:s3:::{name}-{account}-*"
    add(
        "ProjectBuckets",
        [
            "s3:CreateBucket",
            "s3:DeleteBucket",
            "s3:PutBucketVersioning",
            "s3:PutEncryptionConfiguration",
            "s3:PutBucketPublicAccessBlock",
            "s3:PutBucketPolicy",
            "s3:DeleteBucketPolicy",
            "s3:PutBucketTagging",
            "s3:PutLifecycleConfiguration",
            "s3:ListBucket",
            "s3:GetBucketLocation",
        ],
        bucket,
    )
    add(
        "ProjectStateAndArtifacts",
        [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:GetObjectVersion",
            "s3:DeleteObjectVersion",
            "s3:AbortMultipartUpload",
        ],
        bucket + "/*",
    )
    add("CreateTaggedVisitorPool", "cognito-idp:CreateUserPool", "*", request_tags)
    add(
        "ManageTaggedVisitorPool",
        [
            "cognito-idp:" + a
            for a in [
                "UpdateUserPool",
                "DeleteUserPool",
                "CreateUserPoolClient",
                "UpdateUserPoolClient",
                "DeleteUserPoolClient",
                "CreateGroup",
                "UpdateGroup",
                "DeleteGroup",
                "TagResource",
                "AdminCreateUser",
                "AdminSetUserPassword",
                "AdminAddUserToGroup",
                "AdminRemoveUserFromGroup",
                "AdminEnableUser",
                "AdminDisableUser",
                "AdminDeleteUser",
            ]
        ],
        arn("cognito-idp", "userpool/*"),
        resource_tags,
    )
    # Cognito's actual tagging operation uses TagResource in the service authorization model.
    add("CreateTaggedWebsites", "amplify:CreateApp", "*", request_tags)
    add(
        "CreateTaggedDemoBranches",
        "amplify:CreateBranch",
        arn("amplify", "apps/*/branches/demo"),
        request_tags,
    )
    add(
        "ManageTaggedWebsites",
        ["amplify:UpdateApp", "amplify:DeleteApp", "amplify:TagResource"],
        arn("amplify", "apps/*"),
        resource_tags,
    )
    add(
        "PublishTaggedDemoBranches",
        ["amplify:UpdateBranch", "amplify:DeleteBranch", "amplify:TagResource"],
        arn("amplify", "apps/*/branches/demo"),
        resource_tags,
    )
    # Amplify deployment/job child authorization does not include app tags.
    # Limit publishing to this account, region and demo branches; app/branch
    # creation and management above still require Wonderland ownership tags.
    add(
        "PublishDemoDeployments",
        ["amplify:CreateDeployment", "amplify:StartDeployment"],
        [
            arn("amplify", "apps/*/branches/demo/deployments/*"),
            arn("amplify", "apps/*/branches/demo/jobs/*"),
        ],
        regional,
    )
    add(
        "CreateTaggedHTTPAPI",
        "apigateway:POST",
        f"arn:aws:apigateway:{region}::/apis",
        request_tags,
    )
    add(
        "ManageTaggedHTTPAPI",
        ["apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE"],
        [
            f"arn:aws:apigateway:{region}::/apis/*",
            f"arn:aws:apigateway:{region}::/tags/*",
        ],
        resource_tags,
    )
    add(
        "ProjectQueue",
        [
            "sqs:CreateQueue",
            "sqs:DeleteQueue",
            "sqs:SetQueueAttributes",
            "sqs:TagQueue",
            "sqs:UntagQueue",
            "sqs:SendMessage",
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
            "sqs:GetQueueUrl",
        ],
        arn("sqs", name + "-*"),
        regional,
    )
    add(
        "ProjectRuntimeSecrets",
        [
            "secretsmanager:CreateSecret",
            "secretsmanager:PutSecretValue",
            "secretsmanager:UpdateSecret",
            "secretsmanager:GetSecretValue",
            "secretsmanager:DescribeSecret",
            "secretsmanager:DeleteSecret",
            "secretsmanager:RestoreSecret",
            "secretsmanager:TagResource",
            "secretsmanager:UntagResource",
        ],
        arn("secretsmanager", "secret:" + name + "/*"),
        regional,
    )
    log = arn("logs", "log-group:/wonderland/" + name + "*")
    add(
        "ProjectLogs",
        [
            "logs:CreateLogGroup",
            "logs:DeleteLogGroup",
            "logs:PutRetentionPolicy",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
            "logs:TagResource",
            "logs:UntagResource",
        ],
        log,
        regional,
    )
    role = f"arn:aws:iam::{account}:role/{name}-ec2"
    boundary = f"arn:aws:iam::{account}:policy/WonderlandRuntimeBoundary"
    add(
        "CreateBoundedEC2Role",
        "iam:CreateRole",
        role,
        {"StringEquals": {"iam:PermissionsBoundary": boundary}},
    )
    add(
        "ManageOnlyBoundedEC2Role",
        [
            "iam:DeleteRole",
            "iam:TagRole",
            "iam:UntagRole",
            "iam:UpdateAssumeRolePolicy",
            "iam:PutRolePolicy",
            "iam:DeleteRolePolicy",
            "iam:AttachRolePolicy",
            "iam:DetachRolePolicy",
        ],
        role,
    )
    add(
        "ProjectInstanceProfile",
        [
            "iam:CreateInstanceProfile",
            "iam:DeleteInstanceProfile",
            "iam:AddRoleToInstanceProfile",
            "iam:RemoveRoleFromInstanceProfile",
            "iam:TagInstanceProfile",
            "iam:UntagInstanceProfile",
        ],
        f"arn:aws:iam::{account}:instance-profile/{name}-ec2",
    )
    add(
        "PassOnlyDemoRoleToEC2",
        "iam:PassRole",
        role,
        {"StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}},
    )
    docs = [
        f"arn:aws:ssm:{region}::document/" + deployment_details
        for deployment_details in [
            "AWS-RunShellScript",
            "AWS-StartPortForwardingSession",
            "SSM-SessionManagerRunShell",
        ]
    ]
    add(
        "ApprovedServerCommandDocuments",
        ["ssm:SendCommand", "ssm:StartSession"],
        docs,
        regional,
    )
    add(
        "OperateOnlyDemoServer",
        ["ssm:SendCommand", "ssm:StartSession"],
        ec2("instance"),
        resource_tags,
    )
    add(
        "ManageOwnServerSessions",
        ["ssm:ResumeSession", "ssm:TerminateSession"],
        arn("ssm", "session/wonderland-*"),
        regional,
    )
    deploy = {"Version": "2012-10-17", "Statement": statements}
    statements = []
    # Upper bound only; actual role policies still have to grant each permission.
    add(
        "SSMAgent",
        [
            "ssm:DescribeAssociation",
            "ssm:GetDeployablePatchSnapshotForInstance",
            "ssm:GetDocument",
            "ssm:DescribeDocument",
            "ssm:GetManifest",
            "ssm:ListAssociations",
            "ssm:ListInstanceAssociations",
            "ssm:PutInventory",
            "ssm:PutComplianceItems",
            "ssm:PutConfigurePackageResult",
            "ssm:UpdateAssociationStatus",
            "ssm:UpdateInstanceAssociationStatus",
            "ssm:UpdateInstanceInformation",
            "ssmmessages:CreateControlChannel",
            "ssmmessages:CreateDataChannel",
            "ssmmessages:OpenControlChannel",
            "ssmmessages:OpenDataChannel",
            "ec2messages:AcknowledgeMessage",
            "ec2messages:DeleteMessage",
            "ec2messages:FailMessage",
            "ec2messages:GetEndpoint",
            "ec2messages:GetMessages",
            "ec2messages:SendReply",
        ],
        "*",
        regional,
    )
    add(
        "AgentParameters",
        ["ssm:GetParameter", "ssm:GetParameters"],
        [f"arn:aws:ssm:{region}::parameter/*", arn("ssm", "parameter/" + name + "/*")],
        regional,
    )
    add(
        "PullProjectImages",
        [
            "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer",
            "ecr:BatchCheckLayerAvailability",
        ],
        arn("ecr", f"repository/{name}/*"),
        regional,
    )
    add("RegistryAuthentication", "ecr:GetAuthorizationToken", "*", regional)
    add(
        "ProjectArtifacts",
        ["s3:GetObject"],
        f"arn:aws:s3:::{name}-{account}-artifacts/*",
    )
    add(
        "ProjectQueue",
        [
            "sqs:SendMessage",
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
            "sqs:GetQueueUrl",
        ],
        arn("sqs", name + "-*"),
        regional,
    )
    add(
        "ProjectSecretRead",
        "secretsmanager:GetSecretValue",
        arn("secretsmanager", "secret:" + name + "/*"),
        regional,
    )
    add(
        "WriteProjectLogs", ["logs:CreateLogStream", "logs:PutLogEvents"], log, regional
    )
    runtime = {"Version": "2012-10-17", "Statement": statements}

    def actions(row):
        return row["Action"] if isinstance(row["Action"], list) else [row["Action"]]

    compute = [
        row
        for row in deploy["Statement"]
        if all(a.startswith("ec2:") for a in actions(row))
    ]
    services = [row for row in deploy["Statement"] if row not in compute]
    # Managed policies have a 6,144-character limit; account inline user policies
    # have a smaller aggregate limit. Split by purpose rather than widening access.
    access = [
        row
        for row in services
        if row["Sid"]
        in {
            "CreateBoundedEC2Role",
            "ManageOnlyBoundedEC2Role",
            "ProjectInstanceProfile",
            "PassOnlyDemoRoleToEC2",
            "ApprovedServerCommandDocuments",
            "OperateOnlyDemoServer",
            "ManageOwnServerSessions",
        }
    ]
    services = [row for row in services if row not in access]
    result = {
        "WonderlandDemoCompute": {"Version": "2012-10-17", "Statement": compute},
        "WonderlandDemoServices": {"Version": "2012-10-17", "Statement": services},
        "WonderlandDemoAccess": {"Version": "2012-10-17", "Statement": access},
        "WonderlandRuntimeBoundary": runtime,
    }
    for document in result.values():
        if len(json.dumps(document, separators=(",", ":"))) > 6144:
            raise ValueError("Generated document exceeds the managed-policy size limit")
    return result


def dependencies(account):
    """Dependent existing-resource permissions, separate from create request tags."""
    policies(account)  # Reuse the strict account/region/name validation.
    region = "us-east-1"
    tagged = {
        "StringEquals": {
            "aws:RequestedRegion": region,
            "ec2:ResourceTag/Project": "wonderland",
            "ec2:ResourceTag/Stack": "wonderland-demo",
        }
    }
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "UseOwnedVpcForNetworkCreation",
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateSubnet",
                    "ec2:CreateRouteTable",
                    "ec2:CreateSecurityGroup",
                ],
                "Resource": f"arn:aws:ec2:{region}:{account}:vpc/*",
                "Condition": tagged,
            },
            {
                "Sid": "UseOwnedSubnetAndGroupForInterface",
                "Effect": "Allow",
                "Action": "ec2:CreateNetworkInterface",
                "Resource": [
                    f"arn:aws:ec2:{region}:{account}:subnet/*",
                    f"arn:aws:ec2:{region}:{account}:security-group/*",
                ],
                "Condition": tagged,
            },
            {
                "Sid": "ConfigureOwnedVisitorMfa",
                "Effect": "Allow",
                "Action": "cognito-idp:SetUserPoolMfaConfig",
                "Resource": f"arn:aws:cognito-idp:{region}:{account}:userpool/*",
                "Condition": {
                    "StringEquals": {
                        "aws:RequestedRegion": region,
                        "aws:ResourceTag/Project": "wonderland",
                        "aws:ResourceTag/Stack": "wonderland-demo",
                    }
                },
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--output", type=Path, default=Path("secrets/iam-review"))
    parser.add_argument("--dependencies", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    documents = (
        {"WonderlandDemoDependencies": dependencies(args.account)}
        if args.dependencies
        else policies(args.account)
    )
    for name, document in documents.items():
        path = args.output / (name + ".json")
        path.write_text(json.dumps(document, indent=2) + "\n")
        path.chmod(0o600)
        size = len(json.dumps(document, separators=(",", ":")))
        print(f"{name}: {size} characters; saved privately for review")


if __name__ == "__main__":
    main()
