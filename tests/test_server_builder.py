"""Public build source must work for non-root containers without exposing secrets."""
from scripts.simple_builder import prepare_source


def test_extracted_source_becomes_readable_but_credentials_stay_private(tmp_path):
    source=tmp_path/'build-source';source.mkdir(mode=0o700)
    package=source/'scripts';package.mkdir(mode=0o700)
    code=package/'cloud_migrate.py';code.write_text('public source');code.chmod(0o600)
    secret=tmp_path/'docker-config.json';secret.write_text('private');secret.chmod(0o600)
    prepare_source(source)
    assert source.stat().st_mode&0o777==0o755
    assert package.stat().st_mode&0o777==0o755
    assert code.stat().st_mode&0o777==0o644
    assert secret.stat().st_mode&0o777==0o600
