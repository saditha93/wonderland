"""CloudShell provider storage must not consume persistent Terraform state space."""

import importlib.util
from pathlib import Path
import pytest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/terraform/permissions/bootstrap.py"
)
spec = importlib.util.spec_from_file_location("permissions_bootstrap", SOURCE)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_provider_cache_moves_without_moving_state(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    monkeypatch.setattr(bootstrap.tempfile, "gettempdir", lambda: str(temporary))
    (home / "terraform.tfstate").write_text("keep state")
    cache = home / ".terraform"
    cache.mkdir()
    (cache / "partial-provider").write_text("cache only")
    env = bootstrap.provider_environment(home, "459154641936")
    data = Path(env["TF_DATA_DIR"])
    assert data.parent == temporary
    assert (home / "terraform.tfstate").read_text() == "keep state"
    assert not cache.exists()
    assert (
        next(data.glob("previous-home-cache-*/partial-provider")).read_text()
        == "cache only"
    )
    assert data.stat().st_mode & 0o777 == 0o700
    assert bootstrap.provider_environment(home, "459154641936")["TF_DATA_DIR"] == str(
        data
    )


def test_provider_cache_rejects_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap.tempfile, "gettempdir", lambda: str(tmp_path))
    target = tmp_path / "other"
    target.mkdir()
    (tmp_path / f"wonderland-tf-{bootstrap.os.getuid()}-459154641936").symlink_to(
        target
    )
    with pytest.raises(ValueError, match="symlink"):
        bootstrap.provider_environment(tmp_path / "home", "459154641936")
