"""Security constraints for the EC2 demo deployment grants."""
import json
import pytest
from scripts.deployment_policy import policies


def grants(document):
    for row in document['Statement']:
        for action in row['Action'] if isinstance(row['Action'],list) else [row['Action']]:
            yield action,row


def test_every_policy_fits_aws_managed_policy_limit():
    for doc in policies('111111111111').values():
        assert len(json.dumps(doc,separators=(',',':'))) <= 6144


def test_deployer_cannot_grant_itself_access_or_remove_the_role_boundary():
    docs=policies('111111111111')
    rows={action:row for name,doc in docs.items() if name!='WonderlandRuntimeBoundary'
          for action,row in grants(doc)}
    for forbidden in ['iam:PutUserPolicy','iam:AttachUserPolicy','iam:CreatePolicyVersion',
                      'iam:PutRolePermissionsBoundary','iam:DeleteRolePermissionsBoundary','iam:*','*']:
        assert forbidden not in rows
    assert rows['iam:CreateRole']['Condition']['StringEquals']['iam:PermissionsBoundary'].endswith('/WonderlandRuntimeBoundary')
    assert rows['iam:PassRole']['Resource']=='arn:aws:iam::111111111111:role/wonderland-demo-ec2'
    assert rows['iam:PassRole']['Condition']['StringEquals']['iam:PassedToService']=='ec2.amazonaws.com'


def test_instance_launch_requires_tags_allowed_size_and_encrypted_volume():
    rows=policies('111111111111')['WonderlandDemoCompute']['Statement']
    instance=next(row for row in rows if row['Sid']=='LaunchTaggedBoundedInstances')
    assert instance['Condition']['StringEquals']['ec2:InstanceType']==['m7i-flex.large']
    assert instance['Condition']['StringEquals']['aws:RequestTag/Stack']=='wonderland-demo'
    volume=next(row for row in rows if row['Sid']=='LaunchEncryptedVolumes')
    assert volume['Condition']['Bool']['ec2:Encrypted']=='true'
    assert not any(action in {'ec2:ModifyInstanceAttribute','ec2:CreateFleet','ec2:RequestSpotFleet'} for action,_ in grants({'Statement':rows}))


def test_runtime_boundary_excludes_state_and_cloud_administration():
    doc=policies('111111111111')['WonderlandRuntimeBoundary']
    for action,row in grants(doc):
        assert not action.startswith(('iam:','ec2:','amplify:','cognito-idp:','apigateway:'))
        if action.startswith('s3:'):
            assert action=='s3:GetObject'
            assert '-artifacts/' in row['Resource']
        if action.startswith('secretsmanager:'):
            assert action=='secretsmanager:GetSecretValue'
            assert 'secret:wonderland-demo/' in row['Resource']


def test_versioned_artifacts_can_be_cleaned_without_public_bucket_access():
    doc=policies('111111111111')['WonderlandDemoServices']
    row=next(row for action,row in grants(doc) if action=='s3:DeleteObjectVersion')
    assert row['Resource']=='arn:aws:s3:::wonderland-demo-111111111111-*/*'
    publish=next(row for row in doc['Statement'] if row['Sid']=='PublishTaggedDemoBranches')
    assert publish['Resource']=='arn:aws:amplify:us-east-1:111111111111:apps/*/branches/demo'
    children=next(row for row in doc['Statement'] if row['Sid']=='PublishDemoDeployments')
    assert all('/branches/demo/' in arn for arn in children['Resource'])
    assert children['Condition']=={'StringEquals':{'aws:RequestedRegion':'us-east-1'}}
    assert set(children['Action'])=={'amplify:CreateDeployment','amplify:StartDeployment'}
    assert publish['Condition']['StringEquals']['aws:ResourceTag/Project']=='wonderland'


@pytest.mark.parametrize('account,region,name',[
    ('invalid','us-east-1','wonderland-demo'),
    ('111111111111','eu-west-1','wonderland-demo'),
    ('111111111111','us-east-1','production'),
])
def test_unreviewed_target_is_rejected(account,region,name):
    with pytest.raises(ValueError): policies(account,region,name)


def permission_installer():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('permission_installer',Path(__file__).resolve().parents[1]/'scripts/install-demo-permissions.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_requires_approved_digest_before_any_sdk_session(monkeypatch):
    installer=permission_installer()
    calls=[]
    monkeypatch.setattr(installer.boto3,'Session',lambda **kw:calls.append(kw))
    bundle={'account':'111111111111','region':'us-east-1','user':'wonderland','policies':policies('111111111111')}
    with pytest.raises(ValueError,match='approved digest'):
        installer.install(bundle,'unapproved')
    assert calls==[]


def test_installer_rejects_different_target_user_before_sdk_session(monkeypatch):
    installer=permission_installer()
    calls=[]
    monkeypatch.setattr(installer.boto3,'Session',lambda **kw:calls.append(kw))
    bundle={'account':'111111111111','region':'us-east-1','user':'someone-else','policies':policies('111111111111')}
    with pytest.raises(ValueError,match='Unexpected target'):
        installer.install(bundle,installer.checksum(bundle))
    assert calls==[]
