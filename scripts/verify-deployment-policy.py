"""Read-only AWS validation/simulation; never installs IAM policies."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.deployment_policy import policies
from dotenv import dotenv_values
import boto3

root=Path(__file__).resolve().parents[1]
v=dotenv_values(root/'.env',interpolate=False)
s=boto3.Session(aws_access_key_id=v['AWS_ACCESS_KEY_ID'],aws_secret_access_key=v['AWS_SECRET_ACCESS_KEY'],aws_session_token=v.get('AWS_SESSION_TOKEN') or None,region_name='us-east-1')
iam=s.client('iam')
account=s.client('sts').get_caller_identity()['Account']
identity=s.client('sts').get_caller_identity()['Arn']
if not identity.endswith(':user/wonderland'):
    raise SystemExit('Unexpected verifier identity; no mutation performed')
docs=policies(account)
validation={}
for name,document in docs.items():
    findings=s.client('accessanalyzer').validate_policy(policyDocument=json.dumps(document),policyType='IDENTITY_POLICY')['findings']
    validation[name]=[{'type':f['findingType'],'code':f['issueCode']} for f in findings]
    if findings: raise SystemExit('Policy validation needs review: '+name)
base={'aws:RequestedRegion':'us-east-1','aws:ResourceTag/Project':'wonderland',
      'aws:ResourceTag/Stack':'wonderland-demo','ec2:ResourceTag/Project':'wonderland',
      'ec2:ResourceTag/Stack':'wonderland-demo','aws:RequestTag/Project':'wonderland',
      'aws:RequestTag/Stack':'wonderland-demo','ec2:InstanceType':'t4g.medium'}
role=f'arn:aws:iam::{account}:role/wonderland-demo-ec2'
instance=f'arn:aws:ec2:us-east-1:{account}:instance/i-00000000000000000'
boundary=f'arn:aws:iam::{account}:policy/WonderlandRuntimeBoundary'
cases=[
 ('stop-demo','ec2:StopInstances',instance,{},'allowed',False),
 ('stop-other-stack','ec2:StopInstances',instance,{'ec2:ResourceTag/Stack':'other'},'implicitDeny',False),
 ('launch-approved-size','ec2:RunInstances',instance,{},'allowed',False),
 ('launch-expensive-size','ec2:RunInstances',instance,{'ec2:InstanceType':'p5.48xlarge'},'implicitDeny',False),
 ('launch-untagged','ec2:RunInstances',instance,{'aws:RequestTag/Stack':'other'},'implicitDeny',False),
 ('create-bounded-role','iam:CreateRole',role,{'iam:PermissionsBoundary':boundary},'allowed',False),
 ('create-unbounded-role','iam:CreateRole',role,{},'implicitDeny',False),
 ('pass-demo-role','iam:PassRole',role,{'iam:PassedToService':'ec2.amazonaws.com'},'allowed',False),
 ('pass-other-role','iam:PassRole',role+'-other',{'iam:PassedToService':'ec2.amazonaws.com'},'implicitDeny',False),
 ('pass-to-other-service','iam:PassRole',role,{'iam:PassedToService':'lambda.amazonaws.com'},'implicitDeny',False),
 ('remove-boundary','iam:DeleteRolePermissionsBoundary',role,{},'implicitDeny',False),
 ('change-own-permissions','iam:AttachUserPolicy',f'arn:aws:iam::{account}:user/wonderland',{},'implicitDeny',False),
 ('manage-eks','eks:CreateCluster','*',{},'implicitDeny',False),
 ('node-cannot-stop-server','ec2:StopInstances',instance,{},'implicitDeny',True),
 ('node-cannot-read-state','s3:GetObject',f'arn:aws:s3:::wonderland-demo-{account}-state/terraform.tfstate',{},'implicitDeny',True),
 ('node-can-read-artifact','s3:GetObject',f'arn:aws:s3:::wonderland-demo-{account}-artifacts/release.tar.gz',{},'allowed',True),
 ('node-cannot-read-other-secret','secretsmanager:GetSecretValue',f'arn:aws:secretsmanager:us-east-1:{account}:secret:other/password-abcdef',{},'implicitDeny',True),
]
results=[]
for label,action,resource,extra,expected,node in cases:
    context={**base,**extra}
    selected=[doc for name,doc in docs.items() if (name=='WonderlandRuntimeBoundary')==node]
    result=iam.simulate_custom_policy(PolicyInputList=[json.dumps(doc) for doc in selected],
        ActionNames=[action],ResourceArns=[resource],
        ContextEntries=[{'ContextKeyName':k,'ContextKeyValues':[value],'ContextKeyType':'string'} for k,value in context.items()])['EvaluationResults'][0]
    actual=result['EvalDecision']
    results.append({'case':label,'expected':expected,'actual':actual,'passed':actual==expected})
    if actual!=expected: raise SystemExit('Unexpected policy simulation: '+label+' '+actual)
report={'scope':'Read-only AWS ValidatePolicy and SimulateCustomPolicy; no installation/deployment',
        'validation':validation,'simulations':results}
path=root/'docs/evidence/deployment-policy-validation.json'
path.write_text(json.dumps(report,indent=2)+'\n')
print(f'{len(validation)} policies validated with zero findings; {len(results)} allow/deny simulations passed. No permissions changed.')
