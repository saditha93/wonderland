"""Destructive lifecycle guard and interrupted-deployment recovery checks."""
import json
from types import SimpleNamespace
import pytest
from scripts import simple_cloud as cloud
from scripts import simple_cleanup as cleanup


@pytest.mark.parametrize('actions',[['create'],['update'],['delete','create']])
def test_down_never_applies_non_destroy_actions(actions):
    with pytest.raises(ValueError,match='non-destruction'):
        cleanup.require_destroy_only({'resource_changes':[{'address':'aws_instance.demo','change':{'actions':actions}}]})


def test_retry_can_shrink_deletion_scope_but_never_expand_it():
    doc={'resource_changes':[{'address':'aws_s3_bucket.artifacts','change':{'actions':['delete']}}]}
    assert cleanup.require_destroy_only(doc,['aws_instance.demo','aws_s3_bucket.artifacts'])==['aws_s3_bucket.artifacts']
    with pytest.raises(ValueError,match='outside the approved scope'):
        cleanup.require_destroy_only(doc,['aws_instance.demo'])


def test_wrong_down_approval_stops_before_any_backup_or_terraform(tmp_path,monkeypatch):
    monkeypatch.setattr(cleanup,'PRIVATE',tmp_path)
    (tmp_path/'down-review.json').write_text(json.dumps({'review':{},'approval_sha256':'other'}))
    (tmp_path/'reviewed-destroy.tfplan').write_bytes(b'plan')
    monkeypatch.setattr(cleanup,'destroy',lambda *a:pytest.fail('Unexpected deletion'))
    with pytest.raises(ValueError,match='exact teardown approval'): cleanup.down(None,{},'wrong')


def test_active_database_backup_failure_blocks_terraform(tmp_path,monkeypatch):
    monkeypatch.setattr(cleanup,'PRIVATE',tmp_path);(tmp_path/'runtime.json').write_text('{}')
    ec2=SimpleNamespace(describe_instances=lambda **kw:{'Reservations':[{'Instances':[{'State':{'Name':'running'}}]}]})
    s=SimpleNamespace(client=lambda name:ec2)
    def failed(*args): raise ValueError('Backup unavailable')
    monkeypatch.setattr(cleanup,'backup',failed)
    monkeypatch.setattr(cleanup,'tf',lambda *a,**k:pytest.fail('AWS destruction started before backup'))
    with pytest.raises(ValueError,match='Backup unavailable'):
        cleanup.destroy(s,{}, {'instance_id':'i-test'},'destroy-wonderland-demo')


def test_previously_removed_server_does_not_wait_for_unreachable_ssm(tmp_path,monkeypatch):
    monkeypatch.setattr(cleanup,'PRIVATE',tmp_path);(tmp_path/'runtime.json').write_text('{}')
    (tmp_path/'backup.json').write_text('{"preserved":true}')
    s=SimpleNamespace(client=lambda name:SimpleNamespace(describe_instances=lambda **kw:{'Reservations':[]}))
    monkeypatch.setattr(cleanup,'backup',lambda *a:pytest.fail('Cannot back up an absent server'))
    cleanup.backup_if_present(s,{}, {'instance_id':'i-gone'})
    assert json.loads((tmp_path/'backup.json').read_text())=={'preserved':True}
    assert (tmp_path/'backup-unavailable.json').exists()


def test_missing_cleanup_permission_blocks_up_before_any_creation(monkeypatch):
    s=SimpleNamespace(client=lambda name:SimpleNamespace(simulate_principal_policy=lambda **kw:{'EvaluationResults':[{'EvalDecision':'implicitDeny'}]}))
    monkeypatch.setattr(cloud,'plan',lambda *a:pytest.fail('Planning deployment before permission check'))
    monkeypatch.setattr(cloud,'deploy',lambda *a:pytest.fail('Unexpected AWS creation'))
    with pytest.raises(ValueError,match='One-time Terraform permissions'):
        cloud.up(s,{'account_id':'111111111111'},None)


def test_cloud_operations_cannot_overlap(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud,'PRIVATE',tmp_path)
    with cloud.operation_lock():
        with pytest.raises(ValueError,match='Another cloud operation'):
            with cloud.operation_lock(): pass
    with cloud.operation_lock(): pass


def test_build_inputs_are_bound_but_generated_cleanup_override_is_not(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud,'ROOT',tmp_path)
    for name in ['requirements.lock','requirements.in','pyproject.toml','.dockerignore','cloud.sh']:
        (tmp_path/name).write_text('original')
    folder=tmp_path/'infrastructure/terraform/simple';folder.mkdir(parents=True)
    original=cloud.source_hash();(folder/'cleanup_override.tf.json').write_text('{}')
    assert cloud.source_hash()==original
    (tmp_path/'requirements.lock').write_text('different dependencies')
    assert cloud.source_hash()!=original


def test_secret_force_delete_is_prepared_before_destroy():
    assert cleanup.cleanup_override()['resource']['aws_secretsmanager_secret']['runtime']['recovery_window_in_days']==0
