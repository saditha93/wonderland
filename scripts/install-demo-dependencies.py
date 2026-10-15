"""Install only the reviewed dependent-action supplement in administrator CloudShell."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import boto3
from botocore.exceptions import ClientError


def digest(document):
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def install(path,account,approved):
    document=json.loads(path.read_text())
    if not re.fullmatch(r'\d{12}',account) or digest(document)!=approved:
        raise ValueError('Policy/account does not match the reviewed approval')
    session=boto3.Session(region_name='us-east-1')
    if session.client('sts').get_caller_identity()['Account']!=account:
        raise ValueError('Wrong administrator account')
    iam=session.client('iam'); name='WonderlandDemoDependencies'
    if iam.get_user(UserName='wonderland')['User']['Arn']!=f'arn:aws:iam::{account}:user/wonderland':
        raise ValueError('Unexpected user')
    findings=session.client('accessanalyzer').validate_policy(policyDocument=json.dumps(document),policyType='IDENTITY_POLICY')['findings']
    if findings: raise ValueError('AWS policy validation requires review')
    arn=f'arn:aws:iam::{account}:policy/{name}'
    try:
        existing=iam.get_policy(PolicyArn=arn)['Policy']
        old=iam.get_policy_version(PolicyArn=arn,VersionId=existing['DefaultVersionId'])['PolicyVersion']['Document']
        if digest(old)!=approved: raise ValueError('Existing supplement differs; refusing overwrite')
    except ClientError as exc:
        if exc.response['Error']['Code']!='NoSuchEntity': raise
        iam.create_policy(PolicyName=name,PolicyDocument=json.dumps(document),
            Description='Reviewed tagged-network dependencies and Cognito MFA configuration for Wonderland demo',
            Tags=[{'Key':'Project','Value':'wonderland'},{'Key':'Stack','Value':'wonderland-demo'}])
    iam.attach_user_policy(UserName='wonderland',PolicyArn=arn)
    attached={p['PolicyArn'] for p in iam.list_attached_user_policies(UserName='wonderland')['AttachedPolicies']}
    if arn not in attached: raise ValueError('Attachment verification failed')
    print('Verified WonderlandDemoDependencies attached. Existing policies and runtime boundary were not changed.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--policy',type=Path,required=True);p.add_argument('--account',required=True);p.add_argument('--approve',required=True)
    a=p.parse_args()
    try: install(a.policy,a.account,a.approve)
    except (ValueError,ClientError) as exc:
        if isinstance(exc,ValueError): raise SystemExit(str(exc)) from None
        raise SystemExit('AWS dependency-policy installation failed: '+exc.response['Error']['Code']) from None
