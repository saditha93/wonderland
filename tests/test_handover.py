import importlib.util
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("handover", ROOT / "scripts/handover.py")
handover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handover)


@pytest.mark.parametrize("path", ["secrets/local.env", "tmp/postgres/data.json", "docs/course-materials/lecture.md", "frontend/.env.local", "frontend/dist/index.html", ".git/config", "infrastructure/state.tfstate.backup", "infrastructure/demo.tfvars", "../credentials.json", "/private/credentials.json"])
def test_private_and_generated_paths_never_packaged(path):
    assert not handover.allowed(path)


def test_source_archive_excludes_even_tracked_private_files(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for name, content in {
        "start.sh": "#!/bin/sh\necho demo\n",
        "docs/project-report.md": "# Test report\n",
        "frontend/.env.example": "VITE_AUTH_MODE=local\n",
        "secrets/private.json": '{"secret":"PRIVATE_SENTINEL"}',
        "docs/course-materials/private.md": "PRIVATE_COURSE_SENTINEL",
        "frontend/.env.local": "VITE_PRIVATE=PRIVATE_ENV_SENTINEL",
    }.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    handover.create_package()
    with ZipFile(tmp_path / "tmp/handover/wonderland-mvp.zip") as archive:
        assert "wonderland/frontend/.env.example" in archive.namelist()
        assert not any("secrets/" in p or "course-materials/" in p for p in archive.namelist())
        assert all(b"PRIVATE_" not in archive.read(p) for p in archive.namelist())
        assert archive.getinfo("wonderland/start.sh").external_attr >> 16


def test_packaging_refuses_private_key_material():
    marker = "-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5
    with pytest.raises(RuntimeError, match="Private key"):
        handover.validate_text((marker + "\nprivate\n").encode(), "source.py")


def test_handover_works_from_unzipped_source_without_git(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/project-report.md").write_text("# Report\n")
    (tmp_path / "start.sh").write_text("#!/bin/sh\necho demo\n")
    private = tmp_path / "secrets"
    private.mkdir()
    (private / "hidden.json").write_text('{"secret":"DO_NOT_PACKAGE"}')
    handover.create_package()
    with ZipFile(tmp_path / "tmp/handover/wonderland-mvp.zip") as archive:
        assert "wonderland/start.sh" in archive.namelist()
        assert not any("secrets/" in path for path in archive.namelist())
