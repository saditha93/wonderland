"""Apply only the reviewed two-app Amplify deployment-child permission supplement."""
import argparse,copy,hashlib,json
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def install(bundle,approved):
    if checksum(bundle)!=approved or bundle['policy_name']!='WonderlandDemoServices': raise ValueError('Unapproved Amplify update')
    s=boto3.Session(region_name='us-east-1');account=bundle['account'];iam=s.client('iam')
    if s.client('sts').get_caller_identity()['Account']!=account: raise ValueError('Wrong account')
    if iam.get_user(UserName='wonderland')['User']['Arn']!=f'arn:aws:iam::{account}:user/wonderland': raise ValueError('Wrong user')
    if len(bundle['app_ids'])!=2: raise ValueError('Expected only the two reviewed apps')
    for app in bundle['app_ids']:
        arn=f'arn:aws:amplify:us-east-1:{account}:apps/{app}'
        tags=s.client('amplify').list_tags_for_resource(resourceArn=arn)['tags']
        if tags.get('Project')!='wonderland' or tags.get('Stack')!='wonderland-demo': raise ValueError('App ownership differs')
    arn=f'arn:aws:iam::{account}:policy/WonderlandDemoServices';policy=iam.get_policy(PolicyArn=arn)['Policy'];current=iam.get_policy_version(PolicyArn=arn,VersionId=policy['DefaultVersionId'])['PolicyVersion']['Document']
    if current==bundle['after']: print('Reviewed Amplify deployment permissions are already installed.');return
    if checksum(current)!=bundle['before_sha256']: raise ValueError('Existing policy differs from reviewed version')
    expected=copy.deepcopy(current)
    expected['Statement']=[r for r in expected['Statement'] if r['Sid']!='PublishExistingDemoDeploymentChildren']
    statement={'Sid':'PublishExistingDemoDeploymentChildren','Effect':'Allow','Action':['amplify:CreateDeployment','amplify:StartDeployment'],'Resource':[f'arn:aws:amplify:us-east-1:{account}:apps/{a}/branches/demo/{kind}/*' for a in bundle['app_ids'] for kind in ['deployments','jobs']],'Condition':{'StringEquals':{'aws:RequestedRegion':'us-east-1'}}}
    expected['Statement'].append(statement)
    if expected!=bundle['after'] or statement!=bundle['statement']: raise ValueError('Update changes more than the reviewed deployment-child scope')
    document=json.dumps(expected,separators=(',',':'))
    if len(document)>6144: raise ValueError('Policy exceeds managed policy limit')
    if s.client('accessanalyzer').validate_policy(policyDocument=document,policyType='IDENTITY_POLICY')['findings']: raise ValueError('AWS validation requires review')
    iam.create_policy_version(PolicyArn=arn,PolicyDocument=document,SetAsDefault=True)
    v=iam.get_policy(PolicyArn=arn)['Policy']['DefaultVersionId'];verified=iam.get_policy_version(PolicyArn=arn,VersionId=v)['PolicyVersion']['Document']
    if verified!=expected: raise ValueError('Final policy verification failed')
    print('Verified deployment-child publishing for only the two existing Wonderland demo apps. Other grants and runtime boundary are unchanged.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--approve',required=True);a=p.parse_args()
    try: install(json.loads(a.bundle.read_text()),a.approve)
    except (ValueError,ClientError) as exc:
        raise SystemExit(str(exc) if isinstance(exc,ValueError) else 'Amplify permission update failed: '+exc.response['Error']['Code']) from None
