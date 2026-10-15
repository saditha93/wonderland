"""Install an explicitly approved IAM bundle using an administrator's CloudShell.

Does not load .env, create access keys, update existing policy versions, change
billing/account plans, or create compute resources. The target user cannot run
this installer with the proposed deployment grants.
"""
import argparse
import hashlib
import json
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

NAMES = ['WonderlandRuntimeBoundary','WonderlandDemoCompute',
         'WonderlandDemoServices','WonderlandDemoAccess']


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def install(bundle, approved_sha):
    if checksum(bundle) != approved_sha:
        raise ValueError('Bundle does not match the explicitly approved digest')
    if set(bundle['policies']) != set(NAMES) or bundle['user'] != 'wonderland' or bundle['region'] != 'us-east-1':
        raise ValueError('Unexpected target/policy set')
    session=boto3.Session(region_name=bundle['region'])
    account=bundle['account']
    if session.client('sts').get_caller_identity()['Account'] != account:
        raise ValueError('CloudShell belongs to a different AWS account')
    iam=session.client('iam')
    if iam.get_user(UserName=bundle['user'])['User']['Arn'] != f'arn:aws:iam::{account}:user/wonderland':
        raise ValueError('Unexpected target user')
    boundary=f'arn:aws:iam::{account}:policy/WonderlandRuntimeBoundary'
    try:
        role=iam.get_role(RoleName='wonderland-demo-ec2')['Role']
        if role.get('PermissionsBoundary',{}).get('PermissionsBoundaryArn') != boundary:
            raise ValueError('Existing EC2 role is not bounded; review before installing')
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'NoSuchEntity': raise
    # Validate every document and inspect existing definitions before any write.
    missing=[]
    for name in NAMES:
        doc=bundle['policies'][name]
        if len(json.dumps(doc,separators=(',',':'))) > 6144:
            raise ValueError('Managed-policy size limit exceeded')
        findings=session.client('accessanalyzer').validate_policy(
            policyDocument=json.dumps(doc),policyType='IDENTITY_POLICY')['findings']
        if findings: raise ValueError('AWS validation needs review: '+name)
        arn=f'arn:aws:iam::{account}:policy/{name}'
        try:
            existing=iam.get_policy(PolicyArn=arn)['Policy']
            version=iam.get_policy_version(PolicyArn=arn,VersionId=existing['DefaultVersionId'])['PolicyVersion']['Document']
            if checksum(version) != checksum(doc):
                raise ValueError('Existing policy differs; refusing to overwrite '+name)
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'NoSuchEntity': raise
            missing.append(name)
    for name in missing:
        iam.create_policy(PolicyName=name,PolicyDocument=json.dumps(bundle['policies'][name]),
            Description='Reviewed Wonderland EC2 demo '+('runtime permissions boundary' if name.endswith('Boundary') else 'deployment permissions'),
            Tags=[{'Key':'Project','Value':'wonderland'},{'Key':'Stack','Value':'wonderland-demo'}])
        print('Created policy definition: '+name)
    for name in NAMES[1:]:
        iam.attach_user_policy(UserName=bundle['user'],PolicyArn=f'arn:aws:iam::{account}:policy/{name}')
        print('Attached to wonderland: '+name)
    attached={p['PolicyName'] for p in iam.list_attached_user_policies(UserName=bundle['user'])['AttachedPolicies']}
    if not set(NAMES[1:]).issubset(attached):
        raise ValueError('Final attachment verification failed')
    print('Verified all three deployment policies. Runtime boundary is not attached to the user. No compute resources created.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--approve',required=True)
    args=parser.parse_args()
    install(json.loads(args.bundle.read_text()),args.approve)

if __name__=='__main__':
    try: main()
    except (ValueError,ClientError) as exc:
        if isinstance(exc,ValueError): raise SystemExit(str(exc)) from None
        raise SystemExit('IAM operation failed: '+exc.response['Error']['Code']+'; do not assume all grants were installed') from None
